from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from vision import Reading, Note
from controller import Controller

def reading(key='w',kind='pink',size=105,score=8000,reached=False,x=900):
    return Reading(True,score,str(score),reached,note=Note(key,kind,.94,x,340,size,size))

c=Controller()
assert [a.name for a in c.tick(reading(),1)]==['tap']
assert not c.tick(reading(),1.08)
assert not c.tick(reading(score=9050,reached=True),1.16)
assert not c.target
assert not c.tick(reading(score=9050,reached=True),1.24)
assert c.target
assert not c.tick(reading(score=8000),2)
assert not c.tick(Reading(button='retry'),3)
assert [a.name for a in c.tick(Reading(button='retry'),3.1)]==['click']
assert c.rounds==1 and c.target
assert not c.tick(reading(score=9050,reached=True),3.2)  # Old frame cannot reset the latch.
c.tick(reading(score=0,size=50),4)
assert not c.target and not c.await_new

c=Controller()
assert [a.name for a in c.tick(reading(kind='blue'),1)]==['hold']
assert not c.tick(reading(kind='blue'),1.1)
assert [a.name for a in c.suspend()]==['release']
assert not c.held
c=Controller()
assert [a.name for a in c.tick(reading(kind='orange'),1)]==['tap']
assert not c.tick(reading(kind='orange'),1.03)
assert [a.name for a in c.tick(reading(kind='orange'),1.1)]==['tap']
c=Controller(max_rounds=1)
c.tick(reading(),1);c.tick(Reading(button='retry'),2)
assert [a.name for a in c.tick(Reading(button='retry'),2.1)]==['stop']
c=Controller()
assert [a.name for a in c.tick(reading(kind='blue',size=78),1)]==['hold']
assert not c.tick(Reading(True,8000,'8000'),1.3)
assert c.held=='w'
assert not c.tick(reading(key='a',size=55),1.45)
assert c.held=='w'
assert [a.name for a in c.tick(reading(key='a',size=110),1.55)]==['release','tap']
c=Controller()
c.tick(reading(kind='blue',size=78),1)
assert [a.name for a in c.tick(Reading(True,8000,'8000'),2.5)]==['release']
print('PASS: target latch, reset, input modes, release, round limit')
