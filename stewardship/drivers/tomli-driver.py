import tomli


def render(text, plugins):
    # Feed generated text to the TOML parser both as a standalone document
    # and as a value in assignment context, so value-shaped probes
    # (e.g. nested arrays) reach the parser core. TOMLDecodeError is the
    # parser's specified rejection of invalid input, not a defect.
    try:
        tomli.loads(text)
    except tomli.TOMLDecodeError:
        pass
    try:
        tomli.loads("k = " + text)
    except tomli.TOMLDecodeError:
        pass
