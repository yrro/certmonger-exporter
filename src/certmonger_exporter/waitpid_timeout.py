import os
import signal


class Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise Timeout()


def waitpid(pid, options, timeout):
    previous_handler = signal.signal(signal.SIGALRM, _alarm)

    signal.alarm(timeout)
    try:
        result = os.waitpid(pid, options)
        signal.alarm(0)
    finally:
        signal.signal(signal.SIGALRM, previous_handler)

    return result


# vim: ts=8 sts=4 sw=4 et
