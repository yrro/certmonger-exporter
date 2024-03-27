import sys

from certmonger_exporter import * 

configure_logging()
sys.excepthook = excepthook
sys.exit(main(sys.argv))
