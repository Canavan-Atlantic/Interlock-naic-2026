"""Command-line entry point for Modules 5A and 5B."""

import sys

from .retrieval import main as retrieval_main
from .service import main as corpus_main


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in {"inventory", "build", "validate"}:
        return corpus_main(arguments)
    return retrieval_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
