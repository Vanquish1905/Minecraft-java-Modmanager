import sys
import os
import multiprocessing

def main():

    multiprocessing.freeze_support()

    try:
        from config import Config
        from backend import ModManager
        from gui import App
        conf = Config()
        mgr = ModManager(conf)
        app = App(conf, mgr)
        app.mainloop()

    except ImportError as e:
        print(f"Kritischer Fehler: Eine Bibliothek wurde nicht gefunden: {e}")
        if not getattr(sys, 'frozen', False):
            print("\nInstallation mit: pip install customtkinter requests pillow packaging")
      
        input("\nDrücke Enter zum Beenden...")
        sys.exit(1)

    except Exception as e:
        print(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
        input("\nDrücke Enter zum Beenden...")
        sys.exit(1)

if __name__ == "__main__":
    main()
