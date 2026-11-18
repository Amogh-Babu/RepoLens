import sys

from notes_app.service import NotesService


def main(argv):
    service = NotesService()
    if argv[1:2] == ["render"]:
        print(service.render_notes(argv[2]))
        return 0
    print("usage: manage.py render <token>")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
