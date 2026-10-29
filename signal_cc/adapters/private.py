"""The config home and the files in it, readable by the user alone, and never written through a symlink."""
import errno
import os

FLAGS = {"a": os.O_APPEND, "w": os.O_TRUNC, "x": os.O_EXCL}


def home(path):
    """Create the config home 0700 with its parents, or tighten it to 0700 when it is the user's."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = path.stat()
    if st.st_uid == os.getuid() and st.st_mode & 0o077:
        os.chmod(path, st.st_mode & 0o700)


def folder(path):
    """Create a folder 0700 in the home, which exists; one there already must not be a symlink."""
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        if path.is_symlink():
            raise OSError(errno.ELOOP, "a symlink, not followed", str(path)) from None


def open_file(path, mode):
    """Open a file in an existing folder for writing (mode a, w or x, with b for bytes), created 0600,
    never through a symlink."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | FLAGS[mode[0]], 0o600)
    return os.fdopen(fd, mode.replace("x", "w"))
