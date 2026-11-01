"""Ruan Mei lines and local synthesis for the pet; no reference-character audio."""
from pathlib import Path
import hashlib,json,sys,time,urllib.request
root=Path(__file__).resolve().parents[2];pet=root/'desktop-pet'
sys.path.insert(0,str(root/'voice'))
import tts_server
lines=[
['早上好，亲爱的。今天也按自己的步调来。','醒了？先喝些水，再开始今天的事。','晨光正好。今天有什么安排，告诉我吧。'],
['晚上好。忙了一天，先歇一会儿。','亲爱的，今天有值得记住的事吗？','夜色安静下来了。我在这里听你说。'],
['已经很晚了。剩下的事，留给明天吧。','亲爱的，身体也需要休息。别勉强自己。','今天就到这里。睡个好觉，我会在。'],
['吃过饭了吗？别把这一件事忘了。','先吃些东西。工作可以稍等片刻。','忙之前，也照顾好自己的胃口。'],
['回来了。手边的事，我替你看着。','欢迎回来。刚才的安排，我们慢慢接着做。','亲爱的，先坐一会儿吧。'],
['坐得有些久了。起来走几步，如何？','把目光从屏幕上移开，歇一歇。','不必把所有事情挤在同一刻完成。'],
['新的一周开始了。先挑一件最重要的事。','周一也不必着急。把计划分成几步就好。','亲爱的，今天的安排，我们一起看看。'],
['这一周辛苦了。今晚留一点时间给自己。','到周五了。未完成的事，也可以从容收尾。','晚些时候，听首喜欢的歌吧。'],
['周末到了。今天想怎样度过？','没有紧迫的安排，就慢一点也无妨。','天气合适的话，出去走走吧。'],
['有些日子不见了。近来还好吗？','你回来了。愿意和我说说这几天吗？','亲爱的，见到你，我很安心。'],
['生日快乐，亲爱的。愿今天留给你一些美好的记忆。','今天是你的生日。也给自己一小份奖励吧。','新的一岁，不必急着成为别人期待的模样。'],
['要离开一会儿？我记着，路上小心。','今天辛苦了。下次再见，亲爱的。','好，先去休息吧。我会在这里。']]
catalog=json.loads((pet/'renderer/voice-catalog.json').read_text('utf8'))
catalog['revision']='meimei-generated-v1'
for group,texts in zip(catalog['groups'],lines):
    for line,text in zip(group['lines'],texts):line['text']=text
(pet/'renderer/voice-catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf8')
interactions=[]
for prefix,group,texts in [
 ('H','head-pat',['嗯，轻一些就好。','是你啊。我知道了。','头发被弄乱了。容我整理一下。','这样的距离，倒也不坏。','手心很暖。刚忙完吗？','好，留在这里陪你片刻。']),
 ('P','poke',['嗯？我在听。','有什么事，直接告诉我就好。','看见你了，不必着急。','是在提醒我陪你吗？','亲爱的，今天想做些什么？','我没有走神。只是在想你的事。']),
 ('A','poke-annoyed',['好了，先停一停。','你的观察方式，似乎有些特别。','再这样，我要把你的手记下了。','是有什么话，不好直接说吗？','我看见你的恶作剧了。','亲爱的，适可而止。陪我安静一会儿。'])]:
    interactions += [{'id':f'{prefix}{i:02}','groupId':group,'text':text} for i,text in enumerate(texts,1)]
(pet/'renderer/interaction-catalog.json').write_text(json.dumps(interactions,ensure_ascii=False,indent=2),encoding='utf8')
original=(root/'voice/voices.json').read_bytes()
sys.path.insert(0,str(root/'app'))
import desktop
desktop.ensure_services(7788,str(Path.home()/'Documents/rm-workspace'),with_voice=True)
for attempt in range(120):
    try:
        with urllib.request.urlopen('http://127.0.0.1:9881/healthz',timeout=3) as response:
            if json.load(response).get('ok'):break
    except Exception:pass
    if attempt%6==0:print('Waiting for MeiMei voice services',flush=True)
    time.sleep(5)
else:raise RuntimeError('Voice services did not become ready')
done=0
for folder,items in [('voice',[line for g in catalog['groups'] for line in g['lines']]),('interaction-voice',interactions)]:
    directory=pet/'assets'/folder;audio_dir=directory/'audio-final';audio_dir.mkdir(parents=True,exist_ok=True)
    records=[]
    for item in items:
        path=audio_dir/(item['id']+'.wav')
        if not path.is_file():
            request=urllib.request.Request('http://127.0.0.1:7788/api/tts',data=json.dumps({'text':item['text'],'voice':'ruanmei:calm'}).encode('utf8'),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=240) as response:audio=response.read()
            issue=tts_server.wav_quality_issue(audio,item['text']);assert not issue,(item['id'],issue)
            path.write_bytes(audio)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        records.append(dict(item,currentPath=f"audio-final/{item['id']}.wav",currentSha256=digest))
        done+=1;print(f'{done}/54 {folder}/{item["id"]}',flush=True)
        (root/'work/pet-voice-progress.json').write_text(json.dumps({'done':done,'total':54,'last':item['id']}),encoding='utf8')
    (directory/'final-audio-map.json').write_text(json.dumps({'status':'generated','generatedBy':'meimei-local-tts','generatedCount':len(items),'lines':records},ensure_ascii=False,indent=2),encoding='utf8')
assert (root/'voice/voices.json').read_bytes()==original
print('54 generated clips ready; Chinese voice config unchanged',flush=True)
