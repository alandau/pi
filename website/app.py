#!/usr/bin/env python

from flask import Flask, render_template, request, redirect, url_for
import subprocess
import os

PLAYLIST_DIR = '/home/pi/playlists'

app = Flask(__name__)

def get_yt_url(url):
    try:
        args = ['youtube-dl', '-f', 'best[height<=?720]', '-g', '--no-playlist', '--', url]
        return subprocess.check_output(args, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as e:
        return None

@app.route("/")
def main():
    url = request.args.get('url', '')
    if url == 'about:blank':
        url = ''
    done = request.args.get('done', None)
    direct_url = request.args.get('direct_url', None)
    return render_template('index.html', url=url, base=request.base_url, done=done, direct_url=direct_url)

@app.route("/action")
def action():
    url = request.args.get('url', '')
    start_time = request.args.get('start_time')
    direct_url = None
    done = True
    if request.args.get('open', '') or request.args.get('open_and_play', ''):
        player_args = ['/home/pi/player/player.py', url]
        if request.args.get('open_and_play', ''):
            player_args.append('play')
            if start_time:
                player_args.append(start_time)
        subprocess.Popen(player_args, env=dict(os.environ, DISPLAY=":0"))
    elif request.args.get('browser', ''):
        subprocess.Popen(['xdg-open', url], env=dict(os.environ, DISPLAY=":0"))
    elif request.args.get('yt', ''):
        direct_url = get_yt_url(url)
        if not direct_url:
            done = False
    return redirect(url_for('main', url=url, done=done, direct_url=direct_url))

def load_playlist(filename):
    filename = os.path.join(PLAYLIST_DIR, filename)
    with open(filename) as f:
        lines = f.readlines()
    data = []
    if not lines:
        return data
    if lines[0].strip() != '#EXTM3U':
        for l in lines:
            url = l.strip()
            data.append(dict(url=url, title=url))
        return data
    i = 1
    title = None
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if line.startswith('#EXTINF:'):
            split = line[8:].split(',', 1)
            title = split[0] if len(split) == 1 else split[1]
            continue
        url = line
        if not title:
            title = url
        data.append(dict(url=url, title=title))
        title = None
    return data

@app.route("/playlist")
def playlist():
    name = request.args.get('name')
    if not name:
        playlists = [[(f[:-4].decode('utf-8'),url_for('playlist', name=f))] for f in sorted(os.listdir(PLAYLIST_DIR)) if f.endswith('.m3u')]
        return render_template('table.html', columns=['Playlist'], rows=playlists)
    data = load_playlist(name)
    playlist = [[('Play', item['url'] if item['url'].endswith(('.mp4', '.m3u8')) else url_for('getyt', url=item['url'])), (item['title'].decode('utf-8'), None)] for item in data]
    return render_template('table.html', columns=['Play', 'Title'], rows=playlist)

@app.route("/getyt")
def getyt():
    url = request.args.get('url')
    if not url:
        return 'Empty url'
    url = get_yt_url(url)
    if not url:
        return "Can't get video url"
    return redirect(url)

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
