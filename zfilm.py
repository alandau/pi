# coding: utf-8
from __future__ import unicode_literals

import binascii
import re
import json
from collections import OrderedDict

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
    _VALID_URL = r'(?P<id>https?://[^/]*(?:zfilm-hd\.net|kinogo-net\.|kinogo\.eu).*|(zfilm://.*))'

    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
    Cookies = ''

    def _real_extract(self, url):
        headers = {'User-Agent': self.UA, 'Cookie': self.Cookies, 'Accept': '*/*', 'Accept-Encoding': '', 'Accept-Charset': '', 'Accept-Language': ''}
        video_id = self._match_id(url)

        if url.startswith('zfilm://'):
            qs = url[url.index('?')+1:]
            params = compat_parse_qs(qs)
            url = params['url'][0]
            player = params.get('player', ['videocdn'])[0]
            index = int(params['index'][0])
        else:
            player = None
            index = None

        if '//kinogo' in url:
            return self.extract_kinogo(url, video_id, player, index)

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

        title = re.search(r'<meta property="og:title" content="([^"]*)"', main_page)
        title = title.group(1) if title else None

        iframe_url = self._search_regex(r'<iframe .*?src="([^"]+)"', main_page, video_id)
        if iframe_url.startswith('//'):
            iframe_url = 'https:' + iframe_url

        headers['Referer'] = 'https://zfilm-hd.net/'
        iframe_page = self._download_webpage(iframe_url, video_id, headers=headers)

        player_dict = OrderedDict([
                # name: (function, use extract_with_index?)
                ('videocdn', (self.extract_videocdn, True)),
                ('zfilm', (self.extract_zfilm, False)),
        ])

        result = None
        last_exception = None
        if player is not None:
            player_dict = {player: player_dict[player]}
        for name, (func, use_extract) in player_dict.items():
            m = re.search(r'data-src="([^"]*)".*?data-name="%s"' % name, iframe_page)
            if not m:
                continue
            try:
                res = func(m.group(1), iframe_url, video_id, headers, title, index)
            except Exception as e:
                last_exception = e
                continue

            self.postprocess_playlist(res)
            if use_extract:
                res = self.extract_with_index(res, url, name, index)

            if result is None:
                result = res
                if self._downloader.params.get('noplaylist'):
                    break
            elif result.get('_type') == 'playlist':
                if res.get('_type') == 'playlist':
                    result['entries'].extend(res['entries'])
                else:
                    result['entries'].append(res)
            else:
                entries = [result]
                if res.get('_type') == 'playlist':
                    entries.extend(res['entries'])
                else:
                    entries.append(res)
                result = self.playlist_result(entries)
                break

        if last_exception is None and result:
            return result

        raise last_exception

    def extract_with_index(self, result, url, player, index):
        if index is None:
            if 'entries' not in result:
                return result
            for (i, e) in enumerate(result['entries']):
                if 'formats' in e:
                    # Delete formats to prevent the zfilm:// URL below to be overriden to a resolved .mp4 URL
                    del e['formats']
                e['url'] = 'zfilm://?' + compat_urllib_parse_urlencode({'url': url, 'player': player, 'index': i})
            return result
        if 'entries' not in result:
            return result
        return result['entries'][index]

    def postprocess_playlist(self, res):
        # Add mp4 or m3u8 to title
        def update_title(e):
            if 'formats' in e:
                if all(f['url'].endswith('.mp4') for f in e['formats']):
                    e['title'] += ' (mp4)'
                elif all(f['url'].endswith('.m3u8') for f in e['formats']):
                    e['title'] += ' (m3u8)'
            else:
                if e['url'].endswith('.mp4'):
                    e['title'] += ' (mp4)'
                elif e['url'].endswith('.m3u8'):
                    e['title'] += ' (m3u8)'

        if res.get('_type') == 'playlist':
            for e in res['entries']:
                update_title(e)
        else:
            update_title(res)

    def extract_videocdn(self, url, origurl, video_id, headers, playlist_title, index):
        final_page = self._download_webpage(url, video_id, headers=headers)
        videoType = self._search_regex(r'<input type="hidden" id="videoType" value="([^"]*)">', final_page, video_id) # 'movie' or 'tv_series'
        encoded = self._search_regex(r'<input type="hidden" id="files" value="([^"]*)">', final_page, video_id)
        encoded = encoded.replace('&quot;', '"')
        encoded_json = json.loads(encoded, object_pairs_hook=OrderedDict)

        # Get translations
        translations_dict = {}
        default_translation = None
        m = re.search(r'<div class="translations">.*?</div>', final_page, flags=re.S)
        if m:
            s = m.group(0)
            for m in re.finditer(r'<option\s+value="([^"]+)"(\s+selected="selected")?\s*>\s+([^<]+?)\s*</option>', s):
                translations_dict[m.group(1)] = m.group(3)
                if m.group(2) is not None:
                    default_translation = m.group(1)

        userKey = None
        m = re.search(r'var userKey = "([^"]*)"', final_page, flags=re.S)
        if m:
            userKey = m.group(1)
        # translation -> playlist
        d = OrderedDict()
        for (k,v) in encoded_json.items():
            if v.startswith('#'):
                v = v[1:] # discard initial '#'
                hexstr = ''.join(v[i] for i in range(len(v)) if i % 3 != 0)
                d[k] = binascii.unhexlify(hexstr)
            else:
                d[k] = v
            if userKey is not None:
                d[k] = d[k].replace(userKey, ".mp4")

        if default_translation is None and index is not None:
            try:
                default_translation = d.keys()[index]
            except (IndexError, TypeError):
                pass

        def get_one_video_formats(text):
            s = re.sub(r'\[[0-9]+p\]', '', text)
            urls = sorted(set(re.split(r' or |,', s)))
            formats = []
            for u in urls:
                if u.startswith('//'):
                    u = 'https:' + u
                fmt = {'url': u}
                m = re.search(r'/([0-9]+)\.(mp4|m3u8)', u)
                if m:
                    fmt['height'] = int(m.group(1))
                    if m.group(2) == 'm3u8':
                        # For some reason ffmpeg doesn't choose the best resolution (program)
                        # variant from a multi-resolution m3u8 playlist, so do so manually
                        u = u[:-4] + 'mp4:hls:manifest.m3u8'
                        fmt['url'] = u
                formats.append(fmt)
            self._sort_formats(formats)
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
                    title = 'videocdn - {}{} - {}'.format(translation, season_dict['comment'], episode_dict['comment'])
                    formats = get_one_video_formats(episode_dict['file'])
                    entries.append(dict(id=title, title=title, formats=formats))
            return entries

        if videoType == 'movie':
            if index is None and (len(d) == 1 or self._downloader.params.get('noplaylist')):
                if default_translation is not None and default_translation in d:
                    translation = d[default_translation]
                else:
                    translation = next(iter(d.values()))
                formats = get_one_video_formats(translation)
                return {
                    'id': video_id,
                    'title': 'videocdn - ' + video_id,
                    'formats': formats,
                }
            else:
                entries = []
                for (translation, s) in d.items():
                    formats = get_one_video_formats(s)
                    title = 'videocdn - ' + translations_dict.get(translation, translation)
                    entries.append(dict(id=translation, title=title, formats=formats))
                return self.playlist_result(entries)
        if videoType == 'tv_series':
            entries = []
            for (translation, s) in d.items():
                # Ignore translation 0 if other translations present (it's usually a duplicate of another one)
                if translation == '0' and len(d) >= 2:
                    continue
                entries.extend(get_playlist_entries(s, translations_dict.get(translation, translation)))
            return self.playlist_result(entries, playlist_title=playlist_title)
        raise ExtractorError('videocdn unknown videoType {}'.format(videoType))

    def extract_zfilm(self, url, origurl, video_id, headers, playlist_title, index_unused):
        headers['Referer'] = origurl
        final_page = self._download_webpage(url, video_id, headers=headers)
        file_text = self._search_regex(r'file:\s*([^\n]*)', final_page, video_id)

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
                'title': 'zfilm - ' + video_id,
                'formats': formats,
            }

        # playlist
        entries = []
        j = json.loads(file_text)
        for translation_dict in j:
            for season_dict in translation_dict['folder']:
                for episode_dict in season_dict['folder']:
                    title = 'zfilm - {} - {} - {}'.format(translation_dict['title'], season_dict['title'], episode_dict['title'])
                    videourl = episode_dict['file']
                    entries.append(dict(id=videourl, title=title, url=videourl))

        return self.playlist_result(entries, playlist_title=playlist_title)

    def extract_kinogo(self, url, video_id, player, index):
        main_page = self._download_webpage(url, video_id)
        iframe_url = self._search_regex(r'<iframe .*?src="(//vcdn\.icdn\.ws/[^"]+|https://51.tvmovies.in/[^"]+)"', main_page, video_id)
        if iframe_url.startswith('//'):
            iframe_url = 'https:' + iframe_url

        title = re.search(r'<meta property="og:title" content="([^"]*)"', main_page)
        title = title.group(1) if title else None

        res = self.extract_videocdn(iframe_url, iframe_url, video_id, {}, title, index)
        self.postprocess_playlist(res)
        res = self.extract_with_index(res, url, 'kinogo', index)
        return res
