"""PyInstaller-friendly entrypoint for the ALB GUI."""

from tools.manual.alb_gui.window import main


if __name__ == "__main__":
    raise SystemExit(main())
