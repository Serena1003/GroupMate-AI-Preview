from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
im=Image.new('RGB',(1800,1910),'#F7F6FB');d=ImageDraw.Draw(im)
def text(x,y,t,n=25,c='#30334A'):
 for l in t.split('\n'):d.text((x,y),l,font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Unicode.ttf',n),fill=c);y+=int(n*1.6)
def box(x,y,w,h,c):d.rounded_rectangle((x,y,x+w,y+h),radius=18,fill=c)
text(75,35,'GroupMate AI｜课堂演示操作图',52,'#302553');text(80,120,'老师与学生使用课堂网页；XIPU 负责后台 AI 处理',30)
box(75,185,1650,82,'#FFF0DB');text(100,205,'当前：网页按钮已接入；真实 API 尚未连通，全自动运行仍待验证。',28,'#82520A')
xs=[290,780,1270]
for x,t,c in zip(xs,['老师｜教师工作台 / Dashboard','学生｜学生课堂页面','XIPU｜后台处理'],['#E8E1F7','#E1F0EC','#E3EBF8']):box(x,300,455,80,c);text(x+18,318,t,25)
rows=[('01 准备活动','填写目标、案例和讨论任务\n设置 AI 角色与评价规则\n可点击生成设计建议','尚未入组','按老师要求生成设计建议\n返回草案，由老师决定采用'),('02 发布入组','修改并完成九项确认\n发布活动、创建小组\n把邀请码发给学生','输入邀请码与显示名称\n阅读任务和参与说明\n保存个人目标与策略','无需调用 AI\n网页保存活动和参与记录'),('03 讨论挑战','点击 Start 开始\n选择角色，点击\nInvite one response','在聊天框发表和回应观点\n回应 AI 追问或挑战\n共同形成小组方案','按指定角色生成回应\n引擎校验后进入共享讨论'),('04 提交冻结','检查提交及成员确认\n点击 End & freeze\n冻结原始讨论记录','输入小组最终方案\n其他成员分别确认意见\n结束后填写个人自评','不替学生写最终方案\n网页保存原始成果'),('05 评价审核','依次生成：证据 → 独立评价\n核查原话与评价依据\n保存教师采用版本','完成 Reflection\n说明表现、困难和改进方向\n尚不查看个人反馈','提取候选证据、独立评价\n评价不读取私人目标或自评\n返回结果供老师核查'),('06 反馈改进','生成个人、小组、班级报告\n修改时先保存新草案\n审核后点击 Publish','查看本人已发布反馈\n按规则查看小组反馈\n保存 Next action','个人反馈使用教师采用评价\n生成报告草案\n由老师决定最终发布')]
for i,(title,*cells) in enumerate(rows):
 y=415+i*224;text(75,y+48,title,27,'#654593')
 for x,c in zip(xs,cells):
  box(x,y,455,190,'#FFFFFF');text(x+20,y+23,c)
  if i<5:
   d.line((x+227,y+195,x+227,y+215),fill='#B9AECF',width=3);d.polygon([(x+221,y+209),(x+233,y+209),(x+227,y+219)],fill='#B9AECF')
box(75,1785,1650,80,'#E8E1F7');text(100,1804,'学习闭环：设定目标 → 参与讨论 → 自评与反馈 → 调整策略 → 下一轮练习',28,'#4D396D')
p=Path(__file__).resolve().parents[1]/'static/demo-flow.png';im.save(p);print(p)
