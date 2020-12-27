"""
===============
Metadata logger
===============

This module contains functions that process and store the metadata of tracks
played by Liquidsoap.
"""

import logging
import re
from typing import Type, Dict, List, Tuple
from configparser import ConfigParser

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm.session import Session
from sqlalchemy.schema import ForeignKey
from sqlalchemy.orm import relationship

from .db import Base, SessionContext


_log = logging.getLogger(__name__)


class Log(Base):
    __tablename__ = 'log'

    id = Column(Integer, primary_key=True)
    on_air = Column(String, nullable=False, index=True)
    artist = Column(String)
    title = Column(String)
    album = Column(String)
    source = Column(String)
    initial_uri = Column(String)

    extra = relationship("LogExtra", back_populates="log") ### TODO joined pre-load of extra

    @classmethod
    def get(cls, db:Type[Session], start:String=None, end:String=None,
        limit:int=10, chronological:bool=None) -> List:

        query = db.query(cls)

        if start:
            query = query.filter(cls.on_air >= start)
        if end:
            query = query.filter(cls.on_air <= end)

        if chronological:
            query = query.order_by(cls.on_air.asc())
        else:
            query = query.order_by(cls.on_air.desc())

        if not(start and end):
            query = query.limit(limit)

        return [l.to_dict() for l in query]
    
    def to_dict(self):
        d = {'on_air': self.on_air}
        if self.artist:
            d['artist'] = self.artist
        if self.title:
            d['title'] = self.title
        if self.album:
            d['album'] = self.album
        if self.source:
            d['source'] = self.source
        if self.initial_uri:
            d['initial_uri'] = self.initial_uri

        for additional in self.extra:
            d[additional.key] = additional.value

        return d


class LogExtra(Base):
    __tablename__ = 'log_extra'

    id = Column(Integer, primary_key=True)
    log_id = Column(Integer, ForeignKey(
        'log.id', onupdate='CASCADE', ondelete='CASCADE', deferrable=True, initially='DEFERRED'
    ))
    key = Column(String, nullable=False)
    value = Column(String, nullable=False)

    log = relationship("Log", back_populates="extra")



class FieldFilter(object):
    # this is a lazy implementation of a singleton ; in the same program it
    # will always be called with the same config object, so we don't need much
    # thread-safety

    _fields = None
    _wildcards = None

    @classmethod
    def _load(cls, config):
        raw = config['metadata_log']['ignore_fields']
        splitted = raw.split(',')
        # we ignore at least fields from the log table
        fields = set(['on_air', 'artist', 'title', 'album', 'source', 'initial_uri'])
        wildcards = list()
        for entry in splitted:
            if '*' in entry:
                wildcards.append(re.compile(entry.strip().replace('*', '.*')))
            else:
                fields.add(entry.strip())
        cls._fields = fields
        cls._wildcards = wildcards
        _log.debug("Will ignore metadata fields %r", fields)
        _log.debug("Will ignore medadata fields matching %r", wildcards)

    @classmethod
    def filter(cls, config:Type[ConfigParser], data:Dict) -> List[Tuple[str, str]]:
        """
        Extracts metadata entries that fit in our ``log_extra`` table.
        Parameter:
            config: daemon configuration ; we search for ``ignore_fields`` in the ``metadata_log`` section.
            data: as provided by Liquidsoap
        Returns:
            A list of ``(key, value)`` couples, for each key in the input
            dictionary that is not included in ``ignore_fields`` or in the main
            ``log`` table.
        """
        if cls._fields is None:
            cls._load(config)
        result = list()
        for k, v in data.items():
            if k in cls._fields:
                pass
            elif any(rule.match(k) for rule in cls._wildcards):
                pass
            elif k and v:
                result.append((k, v))
        return result


def save_metadata(config:Type[ConfigParser], db:Type[Session], data:Dict):
    """
    Save the metadata provided by Liquidsoap.

    Fields that do not fit into our ``log`` table are saved to ``log_extra``,
    except those matching one in the ``ignore_fields`` configuration.
    Empty values are not saved.
    When ``initial_uri`` is not provided by Liquidsoap, we might use
    ``source_url`` instead (this may happen for example from ``http.input``).
    """
    try:
        log_entry = Log(on_air=data['on_air'])
    except KeyError:
        raise ValueError("Metadata should at least contain on_air")

    for column in ['artist', 'title', 'album', 'source', 'initial_uri']:
        if data.get(column):
            setattr(log_entry, column, data[column])
    if not data.get('initial_uri') and data.get('source_url'):
        log_entry.initial_uri = data['source_url']

    db.add(log_entry)
    db.flush()

    for couple in FieldFilter.filter(config, data):
        db.add(LogExtra(log=log_entry, key=couple[0], value=couple[1]))
