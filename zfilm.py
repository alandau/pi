# coding: utf-8
from __future__ import unicode_literals

import binascii
import re
import json

from .common import InfoExtractor
from ..compat import (
    compat_parse_qs,
    compat_urllib_parse_urlencode,
)
from ..utils import (
    RegexNotFoundError,
    ExtractorError,
)

class ZfilmIE(InfoExtractor):
    IE_NAME = 'zfilm-online'
    IE_DESC = 'Zfilm-Online videos'
    # https://e.zfilm-online.xyz/
    # https://w.online-life-hd.xyz/
    _VALID_URL = r'(?P<id>https?://[a-z0-9-]*\.(?:zfilm-online|online-life-hd)\.xyz/.*|(zfilm://.*))'

    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:62.0) Gecko/20100101 Firefox/62.0'

    def _real_extract(self, url):
        headers = {'User-Agent': self.UA, 'Referer': url}
        video_id = self._match_id(url)

        if url.startswith('zfilm://'):
            qs = url[url.index('?')+1:]
            params = compat_parse_qs(qs)
            url = params['url'][0]
            index = int(params['index'][0])
        else:
            index = None

        def extract_with_index(result, index=index):
            if index is None:
                if 'entries' not in result:
                    return result
                for (i, e) in enumerate(result['entries']):
                    if 'formats' in e:
                        del e['formats']
                    e['url'] = 'zfilm://?' + compat_urllib_parse_urlencode({'url': url, 'index': i})
                return result
            return result['entries'][index]

        main_page = self._download_webpage(url, video_id, headers=headers, expected_status=(200, 301, 302, 404))
        REDIRECT_REGEX = r'[0-9]{,2};\s*(?:URL|url)=\'?([^\'"]+)'
        metare = re.compile(
            r'(?i)<meta\s+(?=(?:[a-z-]+="[^"]+"\s+)*http-equiv="refresh")'
            r'(?:[a-z-]+="[^"]+"\s+)*?content="%s' % REDIRECT_REGEX)
        found = metare.search(main_page)
        old_url = url
        while found:
            refresh_url = found.group(1)
            headers['Referer'] = old_url
            old_url = refresh_url
            main_page = self._download_webpage(refresh_url, video_id, headers=headers, expected_status=(200, 301, 302, 404))
            found = metare.search(main_page)

        iframe_url = self._search_regex(r'<iframe .*?src="([^"]+assistir-filme\.biz/video(?:\?[^"]*)?)"', main_page, video_id)
        headers['Referer'] = iframe_url
        iframe_page = self._download_webpage(iframe_url, video_id, headers=headers)

        videocdn = re.search(r'<script.*?"src":"(https://cdn.720-serie.top/[^"]*)".*?</script', iframe_page)
        if videocdn:
            return extract_with_index(self.extract_videocdn(videocdn.group(1), iframe_url, video_id, headers))

        assistir = re.search(r'<script.*?"src":"(https://[a-z0-9-]*\.assistir-filme\.biz[^"]*)".*?</script', iframe_page)
        if assistir:
            return extract_with_index(self.extract_assistir(assistir.group(1), iframe_url, video_id, headers))

        raise ExtractorError('Not zfilm or assistir-filme')

    def extract_videocdn(self, url, origurl, video_id, headers):
        final_page = self._download_webpage(url, video_id, headers=headers)
        videoType = self._search_regex(r'<input type="hidden" id="videoType" value="([^"]*)">', final_page, video_id) # 'movie' or 'tv_series'
        encoded = self._search_regex(r'<input type="hidden" id="files" value="([^"]*)">', final_page, video_id)
        encoded = encoded.replace('&quot;', '"')
        encoded_json = json.loads(encoded)

        # Get translations
        translations_dict = {}
        default_translation = None
        m = re.search(r'<div class="translations">.*?</div>', final_page, flags=re.S)
        if m:
            s = m.group(0)
            for m in re.finditer(r'<option\s+value="([^"]+)"\s+(selected="selected")?\s*>\s+([^<]+?)\s*</option>', s):
                translations_dict[m.group(1)] = m.group(3)
                if m.group(2) is not None:
                    default_translation = m.group(1)

        # translation -> playlist
        d = {}
        for (k,v) in encoded_json.items():
            v = v[1:] # discard initial '#'
            hexstr = ''.join(v[i] for i in range(len(v)) if i % 3 != 0)
            d[k] = binascii.unhexlify(hexstr)

        def get_one_video_formats(text):
            s = re.sub(r'\[[0-9]+p\]', '', text)
            urls = sorted(set(re.split(r' or |,', s)))
            formats = []
            for u in urls:
                if u.startswith('//'):
                    u = 'https:' + u
                fmt = {'url': u}
                m = re.search(r'/([0-9]+)\.mp4$', u)
                if m:
                    fmt['height'] = int(m.group(1))
                formats.append(fmt)
            return formats

        def get_playlist_entries(text, translation):
            if translation:
                translation = translation + ' - '
            entries = []
            j = json.loads(text)
            if 'folder' not in j[0]:
                # Only episodes, fabricate a season
                j = [dict(comment="Season 1", folder=j)]
            for season_dict in j:
                for episode_dict in season_dict['folder']:
                    title = '{}{} - {}'.format(translation, season_dict['comment'], episode_dict['comment'])
                    formats = get_one_video_formats(episode_dict['file'])
                    entries.append(dict(id=title, title=title, formats=formats))
            return entries

        if videoType == 'movie':
            if len(d) == 1 or self._downloader.params.get('noplaylist'):
                if default_translation is not None and default_translation in d:
                    translation = d[default_translation]
                else:
                    translation = d.values()[0]
                formats = get_one_video_formats(translation)
                return {
                    'id': video_id,
                    'title': video_id,
                    'formats': formats,
                }
            else:
                entries = []
                for (translation, s) in d.items():
                    formats = get_one_video_formats(s)
                    title = translations_dict.get(translation, translation)
                    entries.append(dict(id=translation, title=title, formats=formats))
                return self.playlist_result(entries)
        if videoType == 'tv_series':
            entries = []
            for (translation, s) in d.items():
                entries.extend(get_playlist_entries(s, translations_dict.get(translation, translation)))
            return self.playlist_result(entries)
        raise ExtractorError('videocdn unknown videoType {}'.format(videoType))

    def extract_assistir(self, url, origurl, video_id, headers):
        headers['Referer'] = origurl
        final_page = self._download_webpage(url, video_id, headers=headers)
        file_text = self._search_regex(r'file:([^\n]*)', final_page, video_id)

        if file_text.endswith('\n'):
            file_text = file_text[:-1]
        if file_text.endswith(','):
            file_text = file_text[:-1]
        file_text = file_text[1:-1] # remove quotes

        if not file_text.startswith('['):
            # regular url
            hls_url = file_text
            formats = self._extract_m3u8_formats(hls_url, url)
            self._sort_formats(formats)
            return {
                'id': video_id,
                'title': video_id,
                'formats': formats,
            }

        # playlist
        entries = []
        j = json.loads(file_text)
        for translation_dict in j:
            for season_dict in translation_dict['folder']:
                for episode_dict in season_dict['folder']:
                    title = '{} - {} - {}'.format(translation_dict['title'], season_dict['title'], episode_dict['title'])
                    videourl = episode_dict['file']
                    entries.append(dict(id=videourl, title=title, url=videourl))

        return self.playlist_result(entries)
