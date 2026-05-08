import logging
from pathlib import Path
from .parsers.parser_2025 import Parser2025
from .parsers.parser_2006_2007 import Parser2006_2007
from .parsers.parser_2008_2016 import Parser2008_2016
from .parsers.parser_2017_2024 import Parser2017_2024
from .utils import extract_full_text

logger = logging.getLogger(__name__)

class ParserFactory:

    _strategies = [
        Parser2006_2007,
        Parser2008_2016,
        Parser2017_2024,
        Parser2025
    ]

    @classmethod
    def get_parser(cls, pdf_path: str | Path):
        full_text = extract_full_text(pdf_path)

        for strategy in cls._strategies:
            if strategy.can_handle(full_text):
                logger.info(f"{pdf_path.name} -> {strategy.__name__}")
                return strategy()

        raise ValueError(f"No parser found for {pdf_path}")