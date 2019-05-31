from qbittorrentui.main import Main


def main():
    run()


def run():
    prog = Main()
    try:
        prog.start()
    except Exception:
        # try to print some mildly helpful info about the crash
        import sys
        from pprint import pprint as pp
        exc_type, exc_value, tb = sys.exc_info()
        if tb is not None:
            prev = tb
            curr = tb.tb_next
            while curr is not None:
                prev = curr
                curr = curr.tb_next
            try:
                pp(prev.tb_frame.f_locals)
            except Exception:
                pass

        print()
        prog.cleanup()
        raise


if __name__ == "__main__":
    main()
