"""A real bounded MP4 render plus independent audiovisual approval gates."""
import json
import shutil
import subprocess
import unittest
import test_dissemination as fixtures
from app import app
from models import db
from dissemination_video import DisseminationVideo, process_one
from dissemination_service import asset_root


class DisseminationVideoTests(unittest.TestCase):
    # Reuse fixture helpers without inheriting or repeating the original tests.
    signin=fixtures.DisseminationTests.signin
    create=fixtures.DisseminationTests.create
    process=fixtures.DisseminationTests.process
    ready=fixtures.DisseminationTests.ready
    approve=fixtures.DisseminationTests.approve
    post=fixtures.DisseminationTests.post
    def setUp(self):
        fixtures.DisseminationTests.setUp(self)
        DisseminationVideo.query.delete();db.session.commit()
    def tearDown(self):
        db.session.rollback();DisseminationVideo.query.delete();db.session.commit()
        fixtures.DisseminationTests.tearDown(self)

    def video_action(self,item,**data):
        return self.client.post(f'/admin/divulgacao/{item.id}/video',data=dict(csrf_token='dc-test',**data))

    def test_unapproved_material_cannot_queue_video(self):
        item=self.ready('curiosity')
        self.assertEqual(self.video_action(item,action='generate').status_code,409)
        self.assertEqual(DisseminationVideo.query.count(),0)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg is required for real encoding')
    def test_real_silent_video_requires_separate_approval_and_tracks_source_version(self):
        item=self.ready('curiosity');self.approve(item)
        self.assertEqual(self.video_action(item,action='generate').status_code,302)
        self.assertTrue(process_one())
        video=DisseminationVideo.query.one();self.assertEqual(video.state,'review')
        path=f'/admin/divulgacao/{item.id}/video/{video.id}'
        response=self.client.get(path);self.assertEqual(response.status_code,200);response.close()
        self.assertEqual(self.client.get(path+'?download=1').status_code,403)
        metadata=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_streams','-show_format','-of','json',str(asset_root()/video.name)]))
        self.assertTrue(5.5<=float(metadata['format']['duration'])<=6.5)
        self.assertFalse(any(stream['codec_type']=='audio' for stream in metadata['streams']))
        self.assertEqual(self.video_action(item,action='approve',video_id=video.id,reviewed='yes').status_code,302)
        response=self.client.get(path+'?download=1');self.assertEqual(response.status_code,200);response.close()
        self.post(item.id,'correct',note='Rever a explicação científica.')
        self.assertEqual(self.client.get(path+'?download=1').status_code,409)


if __name__=='__main__':unittest.main()
