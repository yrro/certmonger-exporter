import faulthandler
import sys

from certmonger_exporter import * 

faulthandler.enable()
configure_logging()
sys.excepthook = excepthook
sys.exit(main(sys.argv))
