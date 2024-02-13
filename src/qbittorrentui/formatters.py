def pretty_time_delta(seconds, spaces=False):
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days > 0:
        # return '%dd%dh%dm%ds' % (days, hours, minutes, seconds)
        ret = "%dd %dh" % (days, hours)
    elif hours > 0:
        # return '%dh%dm%ds' % (hours, minutes, seconds)
        ret = "%dh %dm" % (hours, minutes)
    elif minutes > 0:
        ret = "%dm %ds" % (minutes, seconds)
    else:
        ret = "%ds" % seconds
    if spaces is False:
        return ret.replace(" ", "")
    return ret


def natural_file_size(value, binary=False, gnu=False, num_format="%.1f"):
    """
    Format a number of byteslike a human readable filesize (eg. 10 kB).

    By
    default, decimal suffixes (kB, MB) are used.  Passing binary=true will use
    binary suffixes (KiB, MiB) are used and the base will be 2**10 instead of
    10**3.  If ``gnu`` is True, the binary argument is ignored and GNU-style
    (ls -sh style) prefixes are used (K, M) with the 2**10 definition.
    Non-gnu modes are compatible with jinja2's ``filesizeformat`` filter.
    source: https://github.com/luckydonald-forks/humanize/blob/master/humanize/filesize.py
    """
    suffixes = {
        "decimal": ("kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"),
        "binary": ("KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB"),
        "gnu": "KMGTPEZY",
    }
    if gnu:
        suffix = suffixes["gnu"]
    elif binary:
        suffix = suffixes["binary"]
    else:
        suffix = suffixes["decimal"]

    base = 1024 if (gnu or binary) else 1000
    num_of_bytes = float(value)

    if num_of_bytes == 1 and not gnu:
        return "1 B"

    if num_of_bytes < base and not gnu:
        if num_of_bytes > 1000:
            num_of_bytes = base
        else:
            return "%d B" % num_of_bytes
    elif num_of_bytes < base and gnu:
        if num_of_bytes > 1000:
            num_of_bytes = base
        else:
            return "%dB" % num_of_bytes

    for i, s in enumerate(suffix):
        unit = base ** (i + 2)
        # round up to next unit to avoid 4 digit size
        if len(str(int(base * num_of_bytes / unit))) == 4 and num_of_bytes < unit:
            num_of_bytes = unit
        if num_of_bytes < unit:
            break
    if gnu:
        return (num_format + "%s") % ((base * num_of_bytes / unit), s)
    return (num_format + " %s") % ((base * num_of_bytes / unit), s)
