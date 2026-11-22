/* ReDrawable.app's executable (Contents/MacOS/ReDrawable).
 *
 * Runs pc/app.py on the Python bundled in Contents/Resources/python, in this process. Because the
 * process is the .app's own executable, macOS takes the name in the menu bar and the Dock, the
 * icon, and the Accessibility permission from ReDrawable.app, not from "python3".
 *
 * Built by mac/build_app.sh: clang -O2 -o ReDrawable launcher.c (no link to Python: it is
 * loaded with dlopen, so the launcher builds before the runtime is in place).
 */
#include <dlfcn.h>
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef PY_LIB
#define PY_LIB "libpython3.13.dylib"
#endif

int main(int argc, char **argv) {
    char exe[PATH_MAX], real[PATH_MAX], contents[PATH_MAX], home[PATH_MAX], lib[PATH_MAX], app[PATH_MAX];
    uint32_t size = sizeof(exe);
    if (_NSGetExecutablePath(exe, &size) != 0 || !realpath(exe, real)) {
        fprintf(stderr, "ReDrawable: can't find its own path\n");
        return 1;
    }
    /* .../ReDrawable.app/Contents/MacOS/ReDrawable -> .../ReDrawable.app/Contents */
    char tmp[PATH_MAX];
    strncpy(tmp, real, sizeof(tmp));
    strncpy(contents, dirname(dirname(tmp)), sizeof(contents));
    snprintf(home, sizeof(home), "%s/Resources/python", contents);
    snprintf(lib, sizeof(lib), "%s/lib/%s", home, PY_LIB);
    snprintf(app, sizeof(app), "%s/Resources/app/pc/app.py", contents);

    setenv("PYTHONHOME", home, 1);
    setenv("PYTHONNOUSERSITE", "1", 1);       /* nothing from the user's own Python */
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1); /* the .app stays as signed; .pyc are built in */
    unsetenv("PYTHONPATH");

    void *py = dlopen(lib, RTLD_NOW | RTLD_GLOBAL);
    if (!py) {
        fprintf(stderr, "ReDrawable: %s\n", dlerror());
        return 1;
    }
    int (*bytes_main)(int, char **) = (int (*)(int, char **))dlsym(py, "Py_BytesMain");
    if (!bytes_main) {
        fprintf(stderr, "ReDrawable: no Py_BytesMain in %s\n", lib);
        return 1;
    }
    /* python <app.py> [args...]; Finder adds -psn_... on old systems, app.py ignores unknown args */
    char **args = calloc((size_t)argc + 2, sizeof(char *));
    args[0] = real;
    args[1] = app;
    for (int i = 1; i < argc; i++) args[i + 1] = argv[i];
    return bytes_main(argc + 1, args);
}
