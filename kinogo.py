# coding: utf-8
from __future__ import unicode_literals

import re
import itertools
import binascii
import base64
import json
import urllib

from .common import InfoExtractor
from ..compat import (
    compat_str,
    compat_urllib_parse_urlencode,
    compat_parse_qs,
)
from ..utils import (
    determine_ext,
    unified_strdate,
    int_or_none,
    RegexNotFoundError,
)


class KinogoIE(InfoExtractor):
    IE_NAME = 'kinogo'
    IE_DESC = 'Kinogo'
    _VALID_URL = r'https?://kinogo\.(?:[\w]+)/(?P<id>[\d]+)-.*\.html|^kinogo://kinogo\?.*'

    def _real_extract(self, url):
        if url.startswith('kinogo://kinogo?'):
            return self.get_one_episode(url)

        video_id = self._match_id(url)
        main_page = self._download_webpage(url, video_id)

        try:
            filestr = self._search_regex(r'''"file"\s*:\s*"([^"]*)"''', main_page, video_id)
        except RegexNotFoundError as e:
            playliststr = self._search_regex(r'''"pl"\s*:\s*"([^"]*)"''', main_page, video_id)
            return self.get_playlist(url, playliststr)

        urls = re.split('\s*(?:,|or)\s*', filestr)
        urls = sorted(set(urls))
        url = urls[-1]

        return {
            'id': video_id,
            'title': url,
            'url': url,
        }

    def get_playlist(self, url, playliststr):
        entries = []
        playliststr = playliststr.replace("'", '"')
        top = json.loads(playliststr)
        for (i, p1) in enumerate(top['playlist']):
            for (j, p2) in enumerate(p1['playlist']):
                videourl = 'kinogo://kinogo?origurl={origurl}&season={season}&episode={episode}'.format(origurl=urllib.quote(url), season=i, episode=j)
                entries.append(dict(id='a'+str(len(entries)), title='{} {}'.format(p1['comment'], p2['comment']), url=videourl))
        return self.playlist_result(entries)

    def get_one_episode(self, url):
        video_id = url
        qs = url[url.index('?')+1:]
        params = compat_parse_qs(qs)
        origurl = params['origurl'][0]
        season = int(params['season'][0])
        episode = int(params['episode'][0])

        main_page = self._download_webpage(origurl, video_id)
        playliststr = self._search_regex(r'''"pl"\s*:\s*"([^"]*)"''', main_page, video_id)
        playliststr = playliststr.replace("'", '"')

        top = json.loads(playliststr)
        filestr = top['playlist'][season]['playlist'][episode]['file']

        urls = re.split('\s*(?:,|or)\s*', filestr)
        urls = sorted(set(urls))
        url = urls[-1]

        return {
            'id': video_id,
            'title': url,
            'url': url,
        }
