# Try setting up a fault handler to log unexpected exits to a file.
# This includes e.g. coredumps caused by external C modules.
try:
    import atexit
    import faulthandler
    import os

    from PyQt5.QtCore import QStandardPaths

    data_dir = os.path.join(
        QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation),
        "MusicBrainz", "Picard")
    os.makedirs(data_dir, exist_ok=True)

    faultfile = os.path.join(data_dir, 'picard-dump-%i.log' % os.getpid())
    fd = open(faultfile, "w")
    faulthandler.enable(fd)

    def clear_log():
        fd.close()
        os.unlink(faultfile)

    # On an actual crash that triggers the fault handler the exit handler will
    # not get called. That means on a clean exit we will remove the log file
    # but keep it on a crash.
    atexit.register(clear_log)

# Be defensive and start even if registering the fault handler failed.
except:  # noqa: F722
    import sys
    import traceback
    print("Failed setting up crash log.", file=sys.stderr)
    print(traceback.format_exc(), file=sys.stderr)

    if '--debug' in sys.argv or '-d' in sys.argv:
        raise
