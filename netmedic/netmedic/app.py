from netmedic.runtime import parse_args, run


def main():
    args = parse_args()
    run(headless=args.headless)


if __name__ == "__main__":
    main()