from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import agent_server as agent
class MusicQuery(unittest.TestCase):
    def test_explicit_state_query_does_not_reach_the_model_as_a_play_request(self):
        for text in ('查询QQ音乐现在的播放状态，按实际结果告诉我。','看看当前的播放状态','查看音乐状态','现在在放什么歌'):
            self.assertEqual(agent.parse_music_command(text),'status',text)
    def test_play_and_pause_still_work(self):
        self.assertEqual(agent.parse_music_command('帮我放首歌'),'play')
        self.assertEqual(agent.parse_music_command('暂停音乐'),'pause')
if __name__=='__main__':unittest.main()
