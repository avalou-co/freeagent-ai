import sys

from .client import call, login

USAGE = """usage: freeagent-ai <command>

  login    open the approve page in the browser; the user logs in and clicks Approve
  status   check the stored credentials work (prints nothing secret)
"""


def main(argv=None):
    cmd = (argv if argv is not None else sys.argv[1:])[:1]
    if cmd == ["login"]:
        ok = login()
        print("Logged in; credentials saved." if ok else "Login did not complete.")
        return 0 if ok else 1
    if cmd == ["status"]:
        print("ok:", call("GET", "users/me")["user"]["url"])
        return 0
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
