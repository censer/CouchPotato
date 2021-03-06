from app import latinToAscii
from app.config.cplog import CPLog
from app.lib.cron.base import cronBase
from app.lib.library import Library
from app.lib.provider.rss import rss
from app.lib.provider.subtitle.sources.opensubtitles import openSubtitles
from app.lib.provider.subtitle.sources.subscene import subscene
import Queue
import cherrypy
import os
import shutil
import time

subtitleQueue = Queue.Queue()
log = CPLog(__name__)

class SubtitleCron(rss, cronBase, Library):

    config = None
    searchingExisting = 0
    providers = []

    def run(self):
        log.info('SubtitleCron thread is running.')

        self.tempdir = cherrypy.config.get('cachePath')

        # Subtitle providers
        for provider in [subscene, openSubtitles]:
            p = provider(self.config, self.extensions['subtitle'])
            self.providers.append(p)

        timeout = 0.1 if self.debug else 1
        while True and not self.abort:
            try:
                movie = subtitleQueue.get(timeout = timeout)

                #do a search
                self.running = True
                self.search(movie)
                self.running = False

                subtitleQueue.task_done()
            except Queue.Empty:
                pass

        log.info('SubtitleCron shutting down.')

    def conf(self, value):
        return self.config.get('Subtitles', value)

    def isEnabled(self):
        return self.conf('enabled') and self.conf('languages') != ''

    def search(self, movie):

        if not self.isEnabled():
            return

        for provider in self.providers:
            log.info('Search %s for subtitles: %s.' % (provider.name, latinToAscii(movie['folder'])))
            result = provider.find(movie)
            if(result.get('subtitles')):
                subtitleDownloads = result['download'](result)
                if(subtitleDownloads):
                    # Add subtitle to history
                    for sub in result.get('subtitles'):
                        provider.addToHistory(movie['movie'], sub['forFile'], sub['id'], sub)

                    # Move subtitles to movie directory
                    for movieFile in movie['files']:
                        subtitleFile = subtitleDownloads.pop()
                        subtitlePath = os.path.join(movie['path'], movieFile['filename'][:-len(movieFile['ext'])])
                        subtitleExt = os.path.splitext(subtitleFile)[1].lower()[1:]
                        lang = result['language'] + '.' if self.conf('addLanguage') else ''
                        shutil.move(subtitleFile, subtitlePath + lang + subtitleExt)

                    break

    def forDirectory(self, directory):
        log.info('Finding subtitles for: %s' % directory)
        self.searchExisting(directory)

    def searchExisting(self, directory = None):

        if not self.searchingExisting < time.time() - 300 and not self.debug:
            log.info('Just searched for subtitles. Can do a search every 5 minutes.')
            return
        elif not self.isEnabled():
            return

        log.info('Start searching for subtitles.')
        movies = self.getMovies(directory)

        for movie in movies:
            if not movie.get('subtitles'):
                subtitleQueue.put(movie)

        log.info('Done searching for subtitles.')

def startSubtitleCron(config, debug):
    cron = SubtitleCron()
    cron.config = config
    cron.debug = debug
    cron.start()

    return cron
