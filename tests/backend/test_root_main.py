import main


def test_parse_args_defaults_to_backend_only():
    args = main.parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 18081
    assert args.with_frontend is False


def test_parse_args_accepts_frontend_flag():
    args = main.parse_args(["--with-frontend", "--port", "8010"])
    assert args.with_frontend is True
    assert args.port == 8010


def test_parse_args_defaults_to_fixed_frontend_port():
    args = main.parse_args([])
    assert args.frontend_port == 18080


def test_build_frontend_command_uses_resolved_npm_executable():
    command = main.build_frontend_command(18080, npm_executable="C:/node/npm.cmd")
    assert command == ["C:/node/npm.cmd", "run", "dev", "--", "--host", "0.0.0.0", "--port", "18080"]
