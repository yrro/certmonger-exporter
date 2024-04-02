import re
import sys
import string


def main(argv):

    mapping = {}
    for arg in argv[1:]:
        name, sep, value = arg.partition("=")
        if not sep:
            pass

        name, sep, filter_ = name.partition("!")
        if sep:
            if filter_ == "groff_path":
                value = re.sub(r"(/+)(\w)", r"\1\\:\2", value)
                value = re.sub(r"(\w)(\.+)", r"\1\\:\2", value)
                value = re.sub(r"-", r"\-", value)
            elif filter_ == "groff":
                value = re.sub(r"-", r"\-", value)

        mapping[name] = value

    template = string.Template(sys.stdin.read())
    print(template.safe_substitute(mapping))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
