from netmedic.runtime import parse_args, run


def main() -> None:
    args = parse_args()
    if getattr(args, "status", False) or getattr(args, "status_json", False):
        run(
            status=args.status,
            status_json=args.status_json,
            require_privileged=getattr(args, "require_privileged", False),
        )
        return
    run(headless=args.headless)


if __name__ == "__main__":
    main()