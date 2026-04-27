# main_window.py
import threading
import random
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel,  QPushButton, QHBoxLayout, QScrollArea, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QSize, QEvent, QUrl, Signal, Slot
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QIcon
from .video import VideoStream
from .config import FRAME_DIR_GREET, FRAME_DIR_FAREWELL, FRAME_DIR_IDLE, FRAME_DIR_SPEAK, ICON_NO_HEAR, ICON_HEAR, ICON_INTERRUPT, ICON_CLOSE, logger, BACKGROUND_IMAGE, HTML_PATH
from .speech_controller import run_speech_loop, question_queue_stream, choose, is_connected, speech_lock
import queue
from .dialog_service import speak_online_prompt_tts, text_queue, get_summary
import pygame
import math
import os
import signal
import webbrowser


class MainWindow(QMainWindow):
    overlay_text_requested = Signal(str)
    user_text_requested = Signal(str)
    model_text_requested = Signal(str)
    user_text_clear_requested = Signal()
    model_text_clear_requested = Signal()
    all_text_clear_requested = Signal()
    recognition_icon_requested = Signal(bool)

    def __init__(self, window_size : tuple[int, int]):
        super().__init__()

        self.question_queue = queue.Queue()
        self.window_size = window_size

        # 对话框相关属性
        # self.user_text = ""  # 用户输入文本
        self.model_text = ""  # 模型回答文本
        self.dialog_opacity = 0.8  # 对话框透明度
        self.max_text_length = 100  # 最大文本长度

        # 各动画的播放索引
        self.entrance_index = 0
        self.idle_index = 0
        self.speaking_index = 0
        self.waiting_index = 0   # 待唤醒状态帧索引

        # 状态机：状态包括 "waiting"（等待唤醒）、"entrance"（进场）、"idle"（待机）、"speaking"（说话）、"farewell"（告别）、"exit"（退场）
        self.animation_state = "waiting"  # 初始状态
        self.recognizing = False
        self.recognition_thread = None
        self.button = False

        # 设置参数来判断是否是初始状态
        self.waiting_breath_in = False
        self.interrupt_flag = False
        self.engine = None
        self.count = 0 # 记录待机状态的次数

        self.interrupt_recognition = False
        self.is_interrupt = False
                # 当前线程号
        self.current_thread_id = []
        # 当前开启线程数
        self.count_thread = 0

        self.category_map = {
            1: '传统戏剧',
            2: '传统音乐',
            3: '传统美术',
            4: '传统舞蹈',
            5: '传统医药',
            6: '民俗',
            7: '传统技艺',
            8: '曲艺',
            9: '传统体育、游艺与杂技',
            10: '民间文学'
        }

        self.category_items_map = {'民间文学': ['邵原神话群', '董永传说', '玄奘传说', '盘古神话', '河图洛书传说', '杞人忧天传说', '老子传说', '梁祝传说', '盘古神话', '木兰传说', '仙翁庙与悬壶济世传说', '太任传说', '钟繇传说', '陈实传说', '固始方言', '柳下惠传说', '岳飞传说', '王莽撵刘秀传说', '董永与七仙女传说', '大禹传说', '灯谜[安阳灯谜]', '邵雍传说', '汉族叙事长诗《郭丁香》', '夸父神话', '列子传说', '白居易传说', '昆阳之战传说', '孟诜传说', '牛郎织女传说', '墨子传说', '韩愈传说', '叶公传说', '伊尹传说', '马文升传说', '丁兰刻木传说', '竹林七贤传说', '王莽撵刘秀传说', '许慎传说', '牡丹传说', '龙门传说', '黄大王传说', '河图洛书传说', '刘秀传说', '洛神的传说', '王祥卧冰传说', '女娲传说', '潘安的传说', '伊尹传说', '司马懿传说', '先蚕氏嫘祖的传说', '鬼谷子传说', '李少故事', '司马光砸缸故事', '范张鸡黍传说', '葛天氏传说', '伊尹传说', '帝喾传说', '庄子传说', '洛神的传说', '樊哙传说', '老君洞传说', '何瑭传说', '王莽撵刘秀传说', '柳毅的传说', '白朗起义传说', '妙善观音传说', '赵氏孤儿传说', '孔子传说（夏邑祖籍传说）', '女娲传说', '吴道子传说', '王莽撵刘秀传说', '朱襄氏传说', '邵雍传说', '范蠡传说', '大禹神话传说', '黄帝传说', '白蛇闹许仙传说', '相思树的故事', '孙叔敖故事', '董永与七仙女传说', '葛天氏传说', '彭祖传说', '神农传说', '张良传说', '崔莺莺和张生的故事', '许由的传说', '董永与七仙女传说[天仙配故事]', '愚公移山传说', '黄帝传说', '灯谜', '息夫人传说', '亡羊补牢传说', '王莽撵刘秀传说', '姜太公的传说', '王莽撵刘秀传说', '董永与七仙女传说', '仓颉传说', '灵宝黄帝传说', '妙善观音传说', '韩湘子传说', '传统儿歌[洛阳儿歌]', '伊尹传说', ''], '传统戏剧': ['四平调', '宛梆', '目连戏（南乐目连戏）', '大弦戏', '皮影戏（桐柏皮影戏）', '罗卷戏', '四平调', '大平调', '怀梆', '道情戏（太康道情戏）', '大平调', '二夹弦', '大平调', '淮调', '花鼓戏（光山花鼓戏）', '大弦戏', '越调', '越调', '柳子戏', '二夹弦', '罗卷戏\xa0', '二股弦', '越调', '罗卷戏', '曲剧', '落腔', '大平调', '豫剧', '四股弦（五调腔）', '二夹弦[西华笙簧二夹弦]', '落腔', '蒲剧（陕州梆子）', '汉剧', '曲剧（汝州曲剧）', '木偶戏（王氏木偶戏）', '罗卷戏', '坠剧（坠子戏）', '南乐五腔调', '罗卷戏', '山东梆子', '宛梆（老梆子）', '坠剧（坠子戏）', '嗨子戏', '豫剧（祥符调）', '曲剧（洛阳曲子）', '靠山簧', '二夹弦', '枣梆', '汉剧[二簧戏]', '坠剧', '木偶戏[蔡村提偶]', '柳琴戏', '豫剧（豫东调）', '目连戏', '皮影戏', '汉剧', '扬高戏', '杠天神', '越调', '扁担戏', '皮影戏', '大平调', '皮影戏', '木偶戏', '柳琴戏', '靠山簧', '木偶戏', '曲剧（高腿曲子戏）', '木偶戏', '二夹弦', '河阳花鼓戏', '怀梆', '罗卷戏', '豫剧（沙河调）', '四股弦（五调腔）', '皮影戏', '落腔', '怀梆', '皮影戏', '商城花篮戏', '越调', '蒲剧（灵宝蒲剧）', '豫剧（祥符调）', '落腔', '汉剧[庞庄二簧戏]', '怀梆', '四股弦（五调腔）', '二夹弦', '怀梆', '怀梆', '四股弦', '皮影戏[皮影戏]', '地灯戏', '嗨子戏（耍孩儿）', '落腔', '二夹弦', '花鼓戏', '越调', '落腔', '二夹弦', '大辫戏', '木偶戏', '木偶戏', '靠山簧', ''], '传统音乐': ['锣鼓艺术（大铜器）', '信阳民歌', '锣鼓艺术（大铜器）', '西坪民歌', '锣鼓艺术（大铜器）', '古筝艺术（中州筝派）', '江河号子（黄河号子）', '笙管乐（超化吹歌）', '佛教音乐（大相国寺梵乐）', '锣鼓艺术（开封盘鼓）', '锣鼓艺术（中州大鼓）', '板头曲', '唢呐艺术', '唢呐（翟氏唢呐）', '唢呐（马村区唢呐）', '唢呐（沈家唢呐）', '卢氏劳号', '筹音乐', '土硪号子', '沙河船工号子', '轧琴', '淅川锣鼓曲', '丹江号子', '祥营狮鼓', '唢呐（豫东唢呐）', '唢呐（通许唢呐）', '信阳民歌（商城民歌）', '洛阳海神乐', '唢呐（河洛响器）', '锣鼓艺术（丝弦锣鼓）', '大铜器（嵩县大铜器）', '道教音乐', '黄河号子（黄河玉门号子）', '黄河号子（黄河打硪号子）', '十盘', '唢呐（大小搦子）', '唢呐（韩店唢呐）', '十盘', '司马懿得胜鼓', '啸乐（口哨音乐）', '黄河号子[黄河河工号子]', '武陟盘鼓', '黄河号子[黄河船工号子]', '桐柏山歌', '田山十万', '三壁吹打乐', '锣鼓十八番', '锣鼓十八番', '小咚鼓艺术', '筹音乐', '原武盘鼓', '武德镇抬鼓', '郑王词曲', '黄河号子', '大圣鼓', '开封鼓子曲', '八音楼子', ''], '传统美术': ['烙画（南阳烙画）', '泥塑（浚县泥咕咕）', '汴绣', '剪纸（卢氏剪纸）', '泥塑（淮阳泥泥狗）', '灯彩（洛阳宫灯）', '木版年画（滑县木版年画）', '灯彩（汴京灯笼张）', '石雕（方城石猴）', '麦秆剪贴', '朱仙镇木版年画', '玉雕（镇平玉雕）', '剪纸（灵宝剪纸）', '剪纸（辉县剪纸）', '剪纸（彰德刻纸）', '叶雕（陈氏叶雕）', '黄石砚', '秦氏绢艺', '苏奇灯笼画', '剪纸（石林剪纸）', '泥塑（汤阴泥彩塑）', '烙画', '民间剪纸（汤阴剪纸）', '木雕（嵩山木雕）', '沈丘顾家馍', '布艺（唐河布艺）', '灵宝布艺', '卢氏烙画', '黄河澄泥砚', '登封木版年画', '木版年画（云成号木版佛画）', '传统糖塑（吹糖人）', '传统糖塑[吹糖人]', '民间剪纸', '许氏屋兽与砖雕', '木雕（郭潘王木雕）', '泥塑[王忠富泥塑]', '布艺（浚县万福虎）', '民间剪纸（禹州剪纸）', '泥塑（泥猴）', '泥塑（裴氏泥塑）', '面塑（魏氏面塑）', '桃核雕花工艺[桃符制作]', '泥塑（李氏彩塑）', '剪纸（河洛剪纸）', '石雕[浚县石雕]', '木雕（临颍木雕）', '石砚雕刻（会圣宫石砚雕刻）', '布艺（鹿邑虎头鞋虎头帽）', '民间剪纸（观堂剪纸）', '剪纸（召陵区剪纸）', '农民画', '麦秆剪贴（陈氏麦秆画）', '民间剪纸', '民间剪纸（信阳剪纸）', '叶雕（商城叶雕）', '内黄李新张木板年画', '刘井薛氏石刻', '玉雕（南阳玉雕）', '黄河古陶', '木雕（巩义木雕）', '木版年画（李氏木版画）', '木版年画（德胜祥木版年画）', '农民画', '泥塑[赵恩民泥塑]', '泥塑（泥玩民居）', '民间剪纸', '烙画（天中火笔画）', '木雕（夏邑王氏木雕）', '黄河澄泥砚', '滕派蝶画', '木版年画（池家年画）', '麦秆剪贴（殷都区麦秆画）', '糖画', '民间剪纸', '竹编（洛宁竹编）', '面塑（赵氏面塑）', '泥塑（嵩山泥人刘）', '玉雕（密玉俏色雕刻）', '黄河澄泥砚', '民间剪纸', '豫北木版神像画[小杨庄木版年画]', '顺店刺绣', '灵宝刺绣', '泥塑（凉洛寨泥娃娃）', '柘城李秀山泥塑', '布艺（商丘虎头鞋虎头帽）', '虢州石砚', '水晶雕刻', '木雕（李氏木雕）', '灯笼画（内黄灯笼画）', '木雕（封丘木雕）', '毛猴', '王公庄绘画', '虢州石砚', '泥塑[淮滨泥塑（小叫吹）]', '民间剪纸（孟津剪纸）', '面塑', '麦秆剪贴（汝南麦草画）', '许昌张氏传统根艺', '泥塑（李氏祖传泥塑）', '重阳茱萸绛囊', '烙画', '刺绣（新县刺绣）', '剪纸（卫滨区剪纸）', '木雕（社旗木雕）', '香包', '面塑', '石雕（芒山石雕）', '卢氏面塑', '面塑', '卢氏木版年画', '东岸桃核雕花工艺', '黄河澄泥砚（存献澄泥砚）', '泥塑[郸城泥塑]', '木版年画（周家口木版年画）', '淮阳芦苇画', ''], '传统舞蹈': ['灯舞（苏家作龙凤灯舞）', '耍老虎', '官会响锣', '狮舞（槐店文狮子）', '高跷（高抬火轿）', '龙舞（火龙舞）', '狮舞（小相狮舞）', '麒麟舞（睢县麒麟舞）', '跑帷子', '麒麟舞', '杨埠打花棍', '抬阁（王店大装）', '竹马舞[三家村竹马舞]', '南席老虎舞', '扑蝶舞', '艾庄铜器舞', '金龟舞', '鸡毛人逗蟾舞', '鱼拱莲舞', '西平鱼灯', '吕村战鼓舞', '项城肘歌', '龙舞（青龙舞）', '独杆跳', '鱼灯花社舞', '抬阁（高装故事）', '霸王鞭（花棍舞）', '弓子锣舞', '鲤鱼闹莲', '抬阁（曲沟抬阁）', '登封闹阁', '皇杠', '双狮舞', '秧歌（善堂老秧歌）', '抬阁[东蔡庄高抬“故事”]', '跑阵', '狮舞[五花营狮子舞]', '竹马舞[苏羊竹马]', '花伞舞[商城花伞舞]', '抬阁（嵩县高装）', '扑蝶舞（放蝶舞）', '抬阁（崇阳垛子）', '背装（旧县背装）', '豫西狮舞（洛阳市大里王狮舞）', '龙舞[狮龙斗蛛舞]', '高跷（东冯封文武高跷）', '卧拐秧歌', '荥阳笑伞', '狮舞(惠济桥狮舞）', '灯舞（童贯龙灯）', '龙舞[南乐西街龙舞]', '背装（温县背装）', '狮舞（大黄滩舞狮）', '肘阁[宁陵肘歌]', '庆丰花鼓舞', '旱船舞（大泉旱船舞）', '担经挑', '花挑舞', '背装（李源屯背装）', '柳位高跷', '担经挑（经担舞）', '小宋佛高跷', '小冀背桩', '竹马舞[朗公庙竹马]', '踢棒槌', '砖井狮虎舞', '双人旱船舞', '九连灯', '回民秧歌', '竹马舞（民权竹马舞）', '曹屯排鼓', '竹马舞[常平对子马]', '莲花灯舞（荷花灯舞）', '肘阁（石固肘阁）', '霸王鞭（花棍舞）', '狮舞（孟庄狮舞）', '龙舞（老娄庄龙舞）', '哼小车', '云彩灯', '龙舞（板凳龙）', '火绫子[火淋子]', '火绫子（商城杈伞舞）', '大仵民间舞蹈', '玄天锣鼓', '担经挑', '抬阁[五柳集抬阁]', '王家热锣鼓', '齐天圣鼓', '独脚舞[独腿高跷]', '武驴', '独角兽', ''], '传统医药': ['中药炮制技术（四大怀药种植与炮制）', '中医正骨疗法（平乐郭氏正骨法）', '中医诊疗法（宋氏中医外科疗法）', '中医诊疗法（买氏中医外治法）', '中医诊疗法（毛氏济世堂脱骨疽疗法）', '中医诊疗法（张氏经络收放疗法）', '中医正骨疗法（郭氏正骨）', '陈氏痘疹伤寒疗法', '中医正骨疗法（李氏正骨）', '禹州中药加工炮制技艺', '中医正骨疗法[陈氏正骨]', '李氏中医药酒炮制技艺', '中医正骨疗法（鸭李正骨）', '传统膏药[杨氏沙园膏药]', '中医诊疗法（朱氏中医妇科）', '口腔咽喉疾病疗法[纯德堂口疮散]', '传统膏药（张氏正骨膏药制作技艺）', '中医诊疗法（修真堂女科）', '中医正骨疗法（窦氏正骨疗法）', '中医正骨疗法[快庄李氏中医正骨]', '中医诊疗法（广济堂中医妇科）', '针灸铜人', '中医诊疗法（程氏中医肝病疗法）', '刘陈铺齐氏骨科', '口腔咽喉疾病疗法[杜氏口疮治疗技法]', '中医诊疗法（于氏不孕不育疗法）', '中医诊疗法（丁氏喉科疗法）', '传统膏药（老张家膏药制作技艺）', '传统膏药（姚家膏药）', '传统膏药（王氏牵正膏药制作技艺）', '李氏眼药', '中医正骨疗法[刘氏正骨]', '传统膏药[济世堂李占标膏药]', '传统膏药[聂麟郊膏药]', '中医外科[世医堂中医外科]', '中医正骨疗法[杨家正骨疗法]', '传统膏药（鲁氏温舒贴制作技艺）', '烧伤疗法[潘氏烧伤传统疗法]', '象庄秦氏妇科', '传统膏药[黄氏膏药]', '传统膏药（积善堂谢氏拔毒膏制作技艺）', '口腔咽喉疾病疗法[秦李庄周氏口腔咽喉科]', '传统膏药[黄塔膏药]', '董氏中医痹症疗法', '中医诊疗法（张氏皮肤病疗法）', '中医正骨疗法（黄氏正骨法）', '中医正骨疗法（王氏捏骨正筋疗法）', '中医外科[张八卦中医外科]', '中医诊疗法（尹氏中医理气解郁疗法）', '针灸[贵氏针灸]', '传统膏药（李氏膏药）', '中医正骨疗法（界地高氏正骨）', '张氏耳病针灸疗法', '传统膏药（韩氏膏药制作技艺）', '传统膏药[明氏正骨膏药]', '传统膏药（常氏膏药制作技艺）', '口腔咽喉疾病疗法[张氏喉科]', '史家中医药组方', '骨应膏制作技艺', '张氏痔漏疗法', '合水张氏正骨', '黑虎丸', '传统中医骨病疗法（长垣单寨骨科）', '口腔咽喉疾病疗法[杨氏珍珠散治疗口疮技艺]', '柳位同裕堂陈氏传统骨病疗法（柳位陈钞骨科）', '李楼李八先生妇科', '针灸（石氏中医针灸）', '中医诊疗法（樊氏妇科不孕症疗法）', '传统膏药（郭峰膏药制作技艺）', '象庄秦氏妇科', '黄家烧伤药膜', '中医外科（众度堂中医外科疗法）', '中医正骨疗法（范氏骨伤疗法）', '针灸（云氏针灸）', '传统膏药（孟津活血接骨止痛膏制作技艺）', '烧伤疗法[烧伤自然疗法与自然烧伤膏]', '象庄秦氏妇科', '中医诊疗法（"双隆号"咽炎疗法）', '中医传统制剂方法（五更太平丸制备工艺）', '针灸（周氏针灸）', ''], '民俗': ['二十四节气——中国人通过观察太阳周年运动而形成的时间知识体系及其实践', '二十四节气——中国人通过观察太阳周年运动而形成的时间知识体系及其实践', '黄帝祭典（新郑黄帝拜祖祭典）', '庙会（商丘火神台庙会）', '重阳节（上蔡重阳习俗）', '祭典（老子祭典）', '民间信俗（关公信俗）', '药市习俗（禹州药会）', '庙会（浚县正月古庙会）\xa0', '民间社火（浚县民间社火）', '打铁花', '马街书会', '洛阳牡丹花会', '太昊伏羲祭典\u3000', '杜寨书会', '地坑院民俗', '二仙奶奶行水', '鄢陵陈化店茶饮习俗', '中原民居营造习俗', '六月六节俗（舞阳烙焦馍）', '东西常骂社火', '薛氏宗祠祭祖仪式', '九流渡添仓会', '开封菊花花会', '母龙寨祈福习俗', '开封堂倌响堂文化', '民间信俗（香山妙善观音信俗）', '打铁花（打铁梨花）', '放河灯', '洛阳喝汤习俗', '王海鳌山灯会', '医圣张仲景祭祀', '大营社火', '福昌庙会', '灵山庙会', '青龙宫庙会及祈雨习俗', '火神祭祀（滑县半朝銮驾）', '李官寨灯节会', '升旗打酒火', '邘新社亲', '周易文化', '新密溱洧婚俗', '中原传统婚俗（嵩山婚俗）', '伦掌孟村九曲黄河灯展会', '中原传统婚俗（宁陵大搬亲）', '上巳节', '新郑大枣习俗与砑枣技艺', '农历二十四节气', '嫘祖祭典', '高王庙会', '二仙庙会', '火神祭祀（武陟行水）', '重阳文化', '黄龙日盘八卦历', '六月送羊', '汤河洗浴习俗', '郭氏族礼', '卫辉比干祭典', '仓颉庙会', '端午节习俗-槲包', ''], '传统技艺': ['中国传统制茶技艺及其相关习俗', '中国皮影戏', '窑洞营造技艺（地坑院营造技艺）', '鲁山窑烧制技艺（鲁山花瓷烧制技艺）', '登封窑陶瓷烧制技艺\xa0', '当阳峪绞胎瓷烧制技艺\xa0', '汝瓷烧制技艺', '宝剑锻制技艺（棠溪宝剑锻制技艺）\xa0', '金镶玉制作技艺（郏县金镶玉制作技艺）', '小吃制作技艺（逍遥胡辣汤制作技艺）', '钧瓷烧制技艺', '唐三彩烧制技艺', '真不同洛阳水席制作技艺', '汝瓷烧制技艺', '蒸馏酒传统酿造技艺（宝丰酒传统酿造技艺）', '太极拳（和氏太极拳）', '百泉药会', '猪蹄制作技艺（位公辣半蹄制作技艺）', '万古文盛馆羊肉卤制作技艺', '禽类烹制技艺（张氏烧鸡制作技艺）', '醋酿造技艺（五谷醇香醋制作技艺）', '天坛砚', '郑家老粉坊粉皮制作技艺', '豆腐制作技艺', '罗卷戏', '道口正月古庙会', '九天阿胶制作技艺', '曹马芝麻糖制作技艺', '乐器制作技艺（欧营铜器制作技艺）', '酒酿造技艺（双头黄酒酿造技艺）', '商城炖菜烹饪技艺', '长葛绒制作技艺', '档发传统手工制作技艺', '传统面食制作技艺（刘氏空心挂面制作技艺）', '道口锡器制作技艺', '中原棉纺织技艺（王氏老粗布制作技艺）', '传统宴席制作技艺（禹州十三碗）', '上庄姜种植与加工', '传统面食制作技艺（鄢陵吊（高）炉烧饼制作技艺）', '醋酿造技艺（周氏米醋制作技艺）', '毛笔制作技艺[汝阳刘毛笔]', '酒酿造技艺[王氏烧酒酿造技艺]', '牛羊肉烹制技艺[何记牛肉制作技艺]', '野王纻器制作技艺', '闹汤驴肉制作技艺', '鹿邑妈糊制作技艺', '巢础制作技艺', '传拓技艺（唐河传拓技艺）', '猴加官', '槲包制作技艺', '甲骨文摹刻技艺', '大营麻花制作技艺', '金属捶锻工艺（嵩阳宝剑锻造技艺）', '邓瓷烧制技艺', '花生糕制作技艺（白记花生糕制作技艺）', '黑陶制作技艺', '道口烧鸡制作技艺', '金银器制作技艺（银匠张）', '洧川豆腐制作技艺', '风筝制作技艺（宋室风筝）', '北宋官瓷烧制技艺', '大刀面（齐氏大刀面）', '秋油腐乳制作技艺', '密县窑陶瓷烧制技艺', '大槽油制作技艺', '开封又一新糖醋软熘鲤鱼焙面', '中原养蚕织绸技艺[鲁山绸织作技艺]', '传统宴席制作技艺（汝州八大碗）', '开封第一楼小笼灌汤包子', '传统面食制作技艺（安阳捋面制作技艺）', '扒村瓷烧制技艺', '中原棉纺织技艺（刘氏老土布纺织技艺）', '柏山缸制作技艺', '官瓷烧制技艺', '胡辣汤制作技艺（北舞渡胡辣汤制作技艺）', '巩县窑陶瓷烧制技艺', '浚县木旋玩具制作技艺', '合伯宝剑煅造技艺', '制鼓技艺', '传拓技艺（偃师传拓技艺）', '银条种植栽培及烹饪技艺', '醋酿造技艺（郭氏枣醋酿造技艺）', '邓城叶氏猪蹄制作技艺', '黑陶制作技艺', '宋河酒传统酿制技艺', '传统香制作技艺（曲仁里古香制作技艺）', '中牟大白蒜栽培技艺', '传统面食制作技艺（老雒阳面食制作技艺）', '香稻丸种植加工技艺', '笙制作技艺', '中原棉纺织技艺[老粗布织作技艺]', '酱菜腌制技艺[莫家酱菜培制技艺]', '琉璃不对儿制作技艺', '酱菜腌制技艺（井店西瓜豆瓣酱制作技艺）', '传统面食制作技艺（浚县子馍制作技艺）', '醋酿造技艺[王勿桥醋手工制作技艺]', '牛羊肉烹制技艺（铁谢羊肉汤制作技艺）', '传统面食制作技艺（新安烫面角制作技艺）', '酒酿造技艺（豫坡酒酿造技艺）', '十碗席', '鹤壁窑古瓷烧制技艺', '酂城糟鱼制作工艺', '古琴斫制技艺', '荥阳河阴石榴栽培技艺', '金属錾刻技艺', '荥阳霜糖（柿霜糖）制作技艺', '高浮雕传拓技艺', '制鼓技艺（时家牛皮鼓跐鼓技艺）', '麻纸制作技艺（手工造纸）', '制鼓技艺', '淀粉食品制作技艺（滑县粉条制作技艺）', '开封陈家菜', '乐器制作技艺（李家乐器制作技艺）', '芝麻种植及传统小磨香油制作技艺', '传统香制作技艺（耿氏香制作技艺）', '坠胡制作技艺（王氏坠胡制作技艺）', '金顶谢花酥梨栽培和加工技艺', '驴肉制作技艺（辛家五香驴肉制作技艺）', '义兴牌匾制作技艺', '布鞋手工制作技艺[毛底布鞋手工制作技艺]', '武陟油茶制作技艺', '传统面食制作技艺（顿岗油馍制作技艺）', '酒酿造技艺（蔡州酒酿造技艺）', '杜康酿酒工艺', '闹汤驴肉制作技艺', '金属捶锻工艺', '芝麻种植及传统小磨香油制作技艺[朱氏石磨香油制作技艺]', '米醋制作技艺（禹氏）', '柿树栽培及柿饼制作技艺', '醋酿造技艺（冯异米醋酿造技艺）', '装裱修复技艺', '古琴斫制技艺', '杜康酿酒工艺', '唐白瓷烧制技艺', '唐白瓷烧制技艺', '传统面食制作技艺（牛忠喜烧饼制作工艺）', '酒酿造技艺（长垣酎酒酿造技艺）', '长垣烹饪技艺', '传统面食制作技艺（登封焦盖烧饼制作技艺）', '青铜器制作技艺', '古建筑彩绘［朱氏古建筑彩绘］', '毛笔制作技艺[刘腾龙毛笔制作技艺]', '手工造纸技艺（东高高氏古法造纸技艺）', '布鞋手工制作技艺（绣鞋制作技艺）', '传拓技艺（毛氏传拓技艺）', '腐竹制作技艺（大槐林腐竹制作技艺）', '青铜器制作技艺[烟云涧青铜器制作技艺]', '黄河澄泥砚', '传统棚口扎制技艺', '酒酿造技艺（伏牛山黄酒酿造技艺）', '黑陶烧制技艺', '传统面食制作技艺（商丘麻花制作技艺）', '传统面食制作技艺（空心贡面制作技艺）', '芝麻种植及传统小磨香油制作技艺', '毛笔制作技艺（李金梅毛笔制作技艺）', '传统面食制作技艺（长垣油馔制作工艺）', '葛记焖饼制作技艺', '登封芥丝（片）制作技艺', '中原棉布印染技艺[捶草印花技艺]', '陈氏木梳制作技艺', '太平车制作技艺', '绞胎瓷烧制技艺', '牛羊肉烹制技艺（丈地特色羊肉汤制作技艺）', '蔡记蒸饺', '琉璃瓦件烧制技艺', '传统面食制作技艺（郏县饸饹面制作技艺）', '传统香制作技艺（张氏古法手工制香技艺）', '董村木杆称制作技艺', '大周黄蜡制作技艺', '鄢陵古桩蜡梅盆景制作技艺', '黄道窑陶瓷烧制技艺', '制鼓技艺（王氏排鼓制作技艺）', '毛笔制作技艺[郭氏毛笔制作工艺]', '铁锅铸造技艺', '陶瓷酒器烧制技艺', '刀具锻造技艺（胡二刀具锻造技艺）', '钧瓷烧制技艺（神前唐钧烧制技艺）', '乐器制作技艺（胡琴制作技艺）', '腐竹制作技艺（河街腐竹制作技艺）', '淀粉食品制作技艺（禹州粉条制作技艺）', '黑陶制作技艺', '酒酿造技艺（怀帮黄酒酿造技艺）', '毛笔制作技艺[杨集毛笔]', '五里源松花蛋制作技艺', '清化竹器制作技艺', '金银器制作技艺（白马寺金银器制作技艺）', '酒酿造技艺[赊店老酒酿造技艺]', '卢仝煎茶技艺', '手工造纸技艺[白棉纸制作技艺]', '传统面食制作技艺（土炒馍制作技艺）', '冬凌茶制作技艺', '金银器制作技艺（新密银饰锻制技艺）', '清化传统竹扇制作技艺', '李封天目瓷烧制技艺', '酒酿造技艺[黄酒酿造技艺]', '邓瓷烧制技艺', '中原养蚕织绸技艺[拐河丝绸织作技艺]', '罗山大肠汤制作技艺', '传统面食制作技艺（方城烩面制作技艺）', '中原棉纺织技艺[黛眉手织布工艺]', '林氏修面技艺', '风筝制作技艺', '酒酿造技艺[大湖九河黄酒酿造技艺]', '淀粉食品制作技艺（马氏懒渣）', '传统面食制作技艺（郑州烩面制作技艺）', '酱菜腌制技艺[三园斋味合酱菜腌制技艺]', '朱仙镇五香豆腐干制作技艺', '牛羊肉烹制技艺[沙家品味来五香牛肉制作技艺]', '王大昌茉莉花茶制作技艺', '陕州糟蛋', '棉布豆花印染技艺', '开封马豫兴桶子鸡', '禽蛋加工技艺（缠丝鸡蛋）', 'sha汤', '酱菜腌制技艺[大有丰酱菜腌制技艺]', '葡萄栽培与果酒酿造技艺', '张弓酒传统酿制技艺', '胡辣汤制作技艺（逊母口胡辣汤制作技艺）', '丹炻烧制技艺', '金属捶锻工艺（洛阳铲锻造技艺）', '小街锅贴制作技艺', '青铜器制作技艺', '装裱修复技艺', '花生糕制作技艺（凤鸣斋花生糕制作技艺）', '豆腐制作技艺', '牛羊肉烹制技艺（三宝羊肉汤制作技艺）', '传统面食制作技艺（川汇区空心挂面制作技艺）', '黑陶烧制技艺', '耿好卤味烤花生技艺', ''], '曲艺': ['三弦书（南阳三弦书）', '大调曲子', '陕州锣鼓书', '河洛大鼓', '河南坠子', '河南坠子', '三弦书（桐柏三弦书）', '河洛大鼓', '画锅', '大鼓书（鼓词）', '大鼓书（鼓词）', '河洛大鼓', '新野槐书', '蛤蟆嗡', '渔鼓道情', '大鼓书（开封大鼓书）', '大鼓书', '灶书', '豫东琴书[清音]', '永城大铙', '豫东琴书', '鼓琴曲', '渔鼓道情', '三弦书[三弦铰子书]', '大调曲子（墨派大调曲子）', '河南坠子', '三弦书（平调三弦书）', '河南坠子', '豫东琴书', '河南坠子', '渔鼓道情', '丝弦道', '河南坠子', '王屋琴书', '大鼓书（鼓词）', '莲花落', '大鼓书（鼓词）', '渔鼓道情', '河南坠子', '锣鼓书', '三弦书[仪封三弦书]', '大鼓书（鼓词）', '渔鼓道情（郸城道情筒）', ''], '传统体育、游艺与杂技': ['太极拳（陈氏太极拳）', '苌家拳', '心意六合拳', '东北庄杂技', '少林功夫', '撂石锁', '心意六合拳', '幻术（宝丰魔术）', '八极拳（月山八极拳）', '通背拳', '杂技（濮阳杂技）', '查拳', '两仪拳', '余家杂技', '姜家拳', '心意六合拳', '杂技（张氏飞车）', '心意六合拳', '查拳', '王堡枪', '心意六合拳', '大洪拳', '梅花拳', '圣门莲花拳', '南无拳', '梅花拳', '通背拳（通臂拳）', '幻术（赵氏魔术）', '通背滑拳', '梅花拳[梅花拳]', '奇士拳', '二洪拳（大吕二洪拳）', '大洪拳', '太乙拳', '心意六合拳', '岳家拳', '马坡八卦掌', '通背拳（通臂拳）', '忠义门拳', '查拳', '汪家拳', '杂技（洛寨杂技）', '小尚炮捶（炮拳）', '阴阳八卦拳', '心意六合拳', '猴艺', '心意六合拳', '子路八卦拳（白拳）', '杨家枪', '通背拳（通臂拳）', '黄派查拳', '回族七式拳', '转秋[孙氏十六挂转秋]', '八卦拳']}

        self.front_button = None

        self.rotating_width = 0.0
        self.rotating_height = 0.0

        self.init_ui()
        self.connect_ui_signals()
        self.init_workers()
        self.setup_window()

    def setup_window(self):
        """窗口设置。

        调试阶段默认使用普通窗口，方便在 VSCode / 终端旁边查看报错。
        如果以后要切回全屏，在 config.py 里加：
            DEBUG_WINDOW = False
        """
        from . import config as app_config

        debug_mode = getattr(app_config, "DEBUG_WINDOW", True)

        if debug_mode:
            self.resize(1280, 720)
            self.move(100, 60)
            self.setWindowTitle("牡丹非遗数字人 - 调试模式")
            self.setWindowFlags(Qt.Window)
            self.setAttribute(Qt.WA_TranslucentBackground, False)
        else:
            self.showFullScreen()
            self.setWindowFlags(
                Qt.WindowStaysOnTopHint |
                Qt.FramelessWindowHint |
                Qt.X11BypassWindowManagerHint
            )
            self.setAttribute(Qt.WA_TranslucentBackground)

    def init_ui(self):
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧聊天区（包含旋转按钮）
        self.left_panel = QWidget()
        # self.left_panel.setFixedSize(987, 1599)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        # 创建背景标签
        self.background_label = QLabel(self.left_panel)
        self.background_label.lower()  # 将背景标签置于底层

        rotating_widget = RotatingButtonsWidget(
            mainwindow=self,
            parent=self.left_panel,
            radius_x=200,               # 更大水平半轴
            radius_y=450,               # 更大垂直半轴
            num_buttons=10,
            button_radius=30
        )
        left_layout.addWidget(rotating_widget)
        left_layout.addStretch()

        # 创建一个滚动区域
        self.text_scroll_area = QScrollArea(rotating_widget)
        self.text_scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
        """)
        self.text_scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.text_scroll_area.setAttribute(Qt.WA_TranslucentBackground)
        self.text_scroll_area.setAlignment(Qt.AlignCenter)
        self.text_scroll_area.setWidgetResizable(True)

        # 创建容器widget
        self.text_overlay_container = QWidget()
        self.text_overlay_container.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.0);
            border-radius: 15px;
        """)

        # 设置容器布局
        self.text_layout = QVBoxLayout(self.text_overlay_container)
        self.text_layout.setContentsMargins(0, 0, 0, 0)
        self.text_layout.setSpacing(15)
        self.text_layout.setAlignment(Qt.AlignHCenter)  # 新增：水平居中

        # 设置滚动区域的位置和大小（居中）
        self.rotating_width = rotating_widget.width()
        self.rotating_height = rotating_widget.height()

        label_width, label_height = int(self.rotating_width * 0.5), int(self.rotating_height * 0.6)

        label = QLabel(self.text_overlay_container)
        label.setStyleSheet("""
                                QLabel {
                                    background: rgba(30, 30, 30, 0.7);
                                    color: white;
                                    font-size: 24px;
                                    font-weight: bold;
                                    border-radius: 10px;
                                    padding: 5px 5px;
                                }
                                QLabel:hover {
                                    background: rgba(50, 50, 50, 0.8);
                                }
                                """)
        label.setText('\n\n'.join([f'{i}: {value}' for i, value in (self.category_map.items())]))
        label.setAlignment(Qt.AlignLeft)
        label.setFixedSize(label_width, label_height)
        # 添加悬停提示
        label.setToolTip("点击任意类别查看详细信息")
        # 安装事件过滤器以处理鼠标悬停事件
        label.installEventFilter(self)

        self.text_layout.addWidget(label)

        # 设置滚动区域尺寸
        scroll_width = int(self.rotating_width * 0.6)
        scroll_height = int(self.rotating_height * 0.5)
        self.text_scroll_area.setWidget(self.text_overlay_container)
        self.text_scroll_area.resize(scroll_width, scroll_height)
        self.text_scroll_area.move(
            (self.rotating_width - scroll_width) // 2,
            (self.rotating_height - scroll_height) // 2
        )
            # === 添加小按钮到左侧布局最下方 ===
        # 创建一个小按钮
        self.small_button = QPushButton("河南非遗图", self.left_panel)
        self.small_button.setStyleSheet("""
            QPushButton {
                background-color: rgb(166, 27, 41);
                color: white;
                border-radius: 15px;
                font-size: 16px;
                margin: 10px;
            }
            QPushButton:hover {
                background-color: rgb(130, 17, 31);
            }
            QPushButton:pressed {
                background-color: rgb(75, 30, 47); 
            }                            
        """)

        self.small_button.setFixedSize(150, 50)  # 设置按钮大小
        left_layout.addWidget(self.small_button, alignment=Qt.AlignBottom | Qt.AlignCenter)

        # === 添加小按钮的槽函数 ===
        self.small_button.clicked.connect(self.on_small_button_clicked)

        # 右侧视频区
        self.right_panel = QWidget()
        # self.right_panel.setFixedSize(2560-987, 1599)
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label.setStyleSheet("background: transparent; border: none;")
        right_layout.addWidget(self.video_label, alignment=Qt.AlignTop | Qt.AlignRight)
        right_layout.addStretch()

        # 创建按钮容器
        button_container = QWidget()
        button_container.setStyleSheet("""
            QWidget {
                background: transparent;
            }
        """)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(20)
        button_layout.setContentsMargins(0, 0, 0, 0)

        # 设置按钮参数
        button_size = self.window_size[1] // 10  # 按钮尺寸
        icon_margin = button_size // 20   # 图标边距

        # 初始化语音按钮图标
        self.normal_icon = self.load_scaled_icon(ICON_NO_HEAR, button_size - icon_margin*2)
        self.active_icon = self.load_scaled_icon(ICON_HEAR, button_size - icon_margin*2)

        # 语音输入按钮
        self.action_button = QPushButton()
        self.action_button.setFixedSize(button_size, button_size)
        self.action_button.setIcon(self.normal_icon)
        self.action_button.setIconSize(QSize(button_size - icon_margin*2, button_size - icon_margin*2))
        self.action_button.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background-color: transparent;
                padding: {icon_margin}px;
            }}
            QPushButton:hover {{
                background-color: rgba(69, 160, 73, 0.3);
                border-radius: {button_size//2}px;
            }}
            QPushButton:pressed {{
                background-color: rgba(61, 139, 64, 0.3);
            }}
        """)
        self.action_button.setCheckable(True)
        self.action_button.clicked.connect(self.on_button_clicked)

        # 初始化打断按钮
        interrupt_icon = self.load_scaled_icon(ICON_INTERRUPT, button_size - icon_margin*2)
        self.interrupt_button = QPushButton()
        self.interrupt_button.setFixedSize(button_size, button_size)
        self.interrupt_button.setIcon(interrupt_icon)
        self.interrupt_button.setIconSize(QSize(button_size - icon_margin*2, button_size - icon_margin*2))
        self.interrupt_button.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background-color: transparent;
                padding: {icon_margin}px;
            }}
            QPushButton:hover {{
                background-color: rgba(211, 47, 47, 0.3);
                border-radius: {button_size//2}px;
            }}
            QPushButton:pressed {{
                background-color: rgba(183, 28, 28, 0.3);
            }}
        """)
        self.interrupt_button.clicked.connect(self.on_interrupt_clicked)

        # 初始化关闭按钮
        close_icon = self.load_scaled_icon(ICON_CLOSE, button_size - icon_margin*2)
        self.close_button = QPushButton()
        self.close_button.setFixedSize(button_size, button_size)
        self.close_button.setIcon(close_icon)
        self.close_button.setIconSize(QSize(button_size - icon_margin*2, button_size - icon_margin*2))
        self.close_button.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background-color: transparent;
                padding: {icon_margin}px;
            }}
            QPushButton:hover {{
                background-color: rgba(211, 47, 47, 0.3);
                border-radius: {button_size//2}px;
            }}
            QPushButton:pressed {{
                background-color: rgba(183, 28, 28, 0.3);
            }}
        """)
        self.close_button.clicked.connect(self.close_all)
        self.close_button.setAttribute(Qt.WA_TranslucentBackground)

        # 创建文字覆盖层
        self.text_overlay = QLabel()
        self.text_overlay.setAlignment(Qt.AlignCenter)
        self.text_overlay.setStyleSheet(f"""
            QLabel {{
                background: transparent;
                color: black;
                font-size: {button_size // 3}px;
                font-family: Microsoft YaHei;
                padding: 20px;
            }}
        """)
        self.text_overlay.setMinimumSize(400, 100)
        self.text_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        
        # 将按钮和文字覆盖层添加到布局中
        button_layout.addStretch(1)
        button_layout.addWidget(self.text_overlay)
        button_layout.addStretch(1.8)
        button_layout.addWidget(self.interrupt_button)
        button_layout.addWidget(self.action_button)
        button_layout.addWidget(self.close_button)
        button_layout.addStretch(1)  # 右侧弹性空间
        button_container.setLayout(button_layout)

                # 将按钮容器放置在视频标签上
        button_container.setParent(self.video_label)
        # 设置按钮容器在顶部右边
        button_container.setGeometry(
            (self.video_label.width() - (button_size * 3 + self.text_overlay.width() + 80)) // 2,  # 右边位置
            20,  # 距离顶部间距
            self.window_size[0],  # 容器宽度（三个按钮的宽度加上间距）
            button_size + 20  # 容器高度
        )
        button_container.raise_()  # 确保按钮容器在最上层
        

        main_layout.addWidget(self.left_panel)
        main_layout.addWidget(self.right_panel)
        self.setCentralWidget(main_widget)

        # 初始尺寸建议不大于 40% 宽度
        initial_width = self.width() * 0.35
        initial_font_size = initial_width // 10
                # 创建滚动区域
        self.scroll_area1 = QScrollArea(self.video_label)
        self.scroll_area1.setWidgetResizable(True)
        self.scroll_area1.setStyleSheet(f"""
            QScrollArea {{
                background-color:  rgba(0, 0, 0, 150);
                color: white;
                font-size: {initial_font_size}px;
                font-family: Microsoft YaHei;
                border-radius: 10px;
                padding: 15px;
            }}
            QScrollBar:vertical {{
                border: none;
                background: rgba(0, 0, 0, 150);
                width: 8px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 100);
                min-height: 20px;
                border-radius: 4px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        self.user_bubble = QLabel()
        self.user_bubble.setObjectName("user_bubble")
        self.user_bubble.setStyleSheet(f"""
            QLabel {{
                background-color: transparent;
                color: white;
                font-size: {initial_font_size}px;
                font-family: Microsoft YaHei;
            }}
        """)
        self.user_bubble.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.user_bubble.setWordWrap(True)
        # self.user_bubble.setGeometry(30, 100, initial_width, 100)
                # 将model_bubble添加到滚动区域
        self.scroll_area1.setWidget(self.user_bubble)
        # self.scroll_area1.setGeometry(
        #     self.video_label.width() - initial_width - 30,  # 右侧位置
        #     230,  # 距离顶部位置
        #     initial_width,  # 宽度
        #     120   # 高度
        # )

        # 创建滚动区域
        self.scroll_area = QScrollArea(self.video_label)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color:  rgba(0, 0, 0, 150);
                color: white;
                font-size: {initial_font_size}px;
                font-family: Microsoft YaHei;
                border-radius: 10px;
                padding: 15px;
            }}
            QScrollBar:vertical {{
                border: none;
                background: rgba(0, 0, 0, 150);
                width: 8px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 100);
                min-height: 20px;
                border-radius: 4px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        # 创建model_bubble作为滚动区域的子部件
        self.model_bubble = QLabel()
        self.model_bubble.setObjectName("model_bubble")
        self.model_bubble.setStyleSheet(f"""
            QLabel {{
                background-color: transparent;
                color: white;
                font-size: {initial_font_size}px;
                font-family: Microsoft YaHei;
            }}
        """)
        self.model_bubble.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.model_bubble.setWordWrap(True)
        self.model_bubble.setMinimumSize(initial_width, 120)

        # 将model_bubble添加到滚动区域
        self.scroll_area.setWidget(self.model_bubble)
        self.scroll_area.setGeometry(
            self.video_label.width() - initial_width - 30,  # 右侧位置
            230,  # 距离顶部位置
            initial_width,  # 宽度
            120   # 高度
        )

    def init_workers(self):
        self.video_stream = VideoStream(self.window_size)
        # 启动各动画帧的加载线程
        threading.Thread(target=self.video_stream.load_frames, args=(FRAME_DIR_GREET, self.video_stream.greet_frames), daemon=True).start()
        threading.Thread(target=self.video_stream.load_frames, args=(FRAME_DIR_IDLE, self.video_stream.idle_frames), daemon=True).start()
        threading.Thread(target=self.video_stream.load_frames, args=(FRAME_DIR_SPEAK, self.video_stream.speak_frames), daemon=True).start()
        threading.Thread(target=self.video_stream.load_frames, args=(FRAME_DIR_FAREWELL, self.video_stream.farewell_frames), daemon=True).start()

        self.frame_timer = QTimer()
        self.frame_timer.timeout.connect(self.update_display)
        self.frame_timer.start(33)

    def connect_ui_signals(self):
        """把后台线程发来的 UI 请求转交给 Qt 主线程处理。"""
        self.overlay_text_requested.connect(self._set_overlay_text)
        self.user_text_requested.connect(self._set_user_text)
        self.model_text_requested.connect(self._set_model_text)
        self.user_text_clear_requested.connect(self._clear_user_text)
        self.model_text_clear_requested.connect(self._clear_model_text)
        self.all_text_clear_requested.connect(self._clear_texts)
        self.recognition_icon_requested.connect(self._set_recognition_icon)

    def set_overlay_text(self, text : str):
        """设置覆盖层文字内容"""
        self.overlay_text_requested.emit(text)

    @Slot(str)
    def _set_overlay_text(self, text: str):
        self.text_overlay.setText(text)

    def get_frame_for_state(self, state : str) -> QImage | None:
        """根据状态获取当前帧，并更新播放索引"""
        
        if state == "entrance":
            if self.video_stream.greet_frames:
                frame = self.video_stream.greet_frames[self.entrance_index % len(self.video_stream.greet_frames)]
                self.entrance_index += 1
                return frame
        elif state == "waiting":
            if self.video_stream.idle_frames:
                frame = self.video_stream.idle_frames[self.waiting_index % len(self.video_stream.idle_frames)]
                self.waiting_index += 1
                return frame
            else:
                return QImage(self.window_size[0], self.window_size[1], QImage.Format_ARGB32)
        elif state == "idle":
            if self.video_stream.idle_frames:
                frame = self.video_stream.idle_frames[self.idle_index % len(self.video_stream.idle_frames)]
                self.idle_index += 1
                return frame
            return None
        elif state == "speaking":
            if self.video_stream.speak_frames:
                frame = self.video_stream.speak_frames[self.speaking_index % len(self.video_stream.speak_frames)]
                self.speaking_index += 1
                return frame
        # elif state == "farewell":
        #     if self.video_stream.farewell_frames:
        #         if self.farewell_index < len(self.video_stream.farewell_frames):
        #             frame = self.video_stream.farewell_frames[self.farewell_index]
        #             self.farewell_index += 1
        #             return frame
        #         else:
        #             self.animation_state = "exit"
        #             self.exit_index = 0
        #             return None
        # elif state == "exit":
        #     if self.video_stream.exit_frames:
        #         if self.exit_index < len(self.video_stream.exit_frames):
        #             frame = self.video_stream.exit_frames[self.exit_index]
        #             self.exit_index += 1
        #             return frame
        #         else:
        #             return None
        return None

    def update_display(self):
        frame = None
        
        # "等待唤醒"状态（播放呼吸动画并叠加提示文字）
        if self.animation_state == "waiting":
            if self.video_stream.idle_frames:
                frame = self.video_stream.idle_frames[self.waiting_index % len(self.video_stream.idle_frames)]
                self.waiting_index += 1
                composite = QImage(frame)
            else:
                composite = QImage(self.window_size[0], self.window_size[1], QImage.Format_ARGB32)
                composite.fill(QColor(0, 0, 0, 0))
            
            painter = QPainter(composite)
            if not self.waiting_breath_in:
                painter.setPen(Qt.white)
                painter.setFont(QFont("华文行楷", 32))
                rect = composite.rect().adjusted(0, 0, 0, -100)
                painter.drawText(rect, Qt.AlignBottom | Qt.AlignHCenter, "喊我名字牡丹来唤醒我")
            painter.end()
            self.video_label.setPixmap(QPixmap.fromImage(composite))
            self.video_label.repaint()
            return

        # 其它状态动画处理
        if self.animation_state == "entrance":
            frame = self.get_frame_for_state("entrance")
            if frame:
                composite = QImage(frame)
                if self.entrance_index >= len(self.video_stream.greet_frames):
                    self.animation_state = "idle"
                    self.current_idle_frames = None
        elif self.animation_state == "idle":
            frame = self.get_frame_for_state("idle")
            if frame:
                composite = QImage(frame)
        elif self.animation_state == "speaking":
            frame = self.get_frame_for_state("speaking")
            if frame:
                composite = QImage(frame)

        if frame:
            # 绘制对话框
            painter = QPainter(composite)
            
            # 设置字体
            font = QFont("华文行楷", 20)
            painter.setFont(font)
            
            painter.end()
            self.video_label.setPixmap(QPixmap.fromImage(composite))
            self.video_label.repaint()

    def send_query(self):
        query = ''
        # if self.button:
        query = question_queue_stream.get()
        logger.info(f"query: {query}")
            
        if not query:
            return

        # 设置用户输入文本
        self.clear_user_text()
        self.set_user_text(query)

        # 在等待唤醒状态下，只处理唤醒指令
        if self.animation_state == "waiting":
            logger.info("The waiting state is becoming entrance")
            if "牡丹" in query or '牡' in query or '丹' in query :
                self.animation_state = "entrance"
                self.entrance_index = 0

    def on_stream_finished(self):
        self.animation_state = "waiting"
        self.waiting_index = 0
        # 清除对话文本
        self.clear_texts()

    # def closeEvent(self, event : QCloseEvent):
    #     self.video_stream.stop()
    #     event.accept()

    def on_button_clicked(self):
        logger.info("The sound recognition button is clicked")
        # is_checked = self.action_button.isChecked()
        
        # 切换图标
        # self.action_button.setIcon(self.active_icon if is_checked else self.normal_icon)
        # 在这里添加按钮2的处理逻辑
        if self.recognizing:
            self.button = False
            self.set_recognition_icon(False)
            # self.add_icon("assets/icons/hear.png")
            self.stop_recognition()
        else:
            self.button = False
            # self.add_icon("assets/icons/no_hear.png")
            self.set_recognition_icon(True)
            self.start_recognition()

    def start_recognition(self):
        logger.info("Start recognition")
        """启动语音识别"""
        self.set_overlay_text("等我打开耳朵")
        self.interrupt_recognition = False
        if not self.recognizing:
            if  self.count_thread:
                self.current_thread_id[self.count_thread-1] = 1
            self.count_thread += 1
            self.current_thread_id.append(2)
            self.recognizing = True
            self.recognition_thread = threading.Thread(
                target=run_speech_loop,
                args=(self,),
                daemon=True
            )
            self.recognition_thread.start()
            # self.action_button.setText("停止聆听")
    
    def stop_recognition(self):
        logger.info("Stop recognition")
        self.set_overlay_text("已经停止聆听···")
        """中止语音识别"""
        self.interrupt_recognition = True
        self.current_thread_id[self.count_thread-1] = 0
        if self.recognizing:
            self.recognizing = False
            if self.recognition_thread and self.recognition_thread.is_alive():
                try:
                    self.recognition_thread.join(timeout=0.1)  # 设置较短的超时时间
                except Exception as e:
                    logger.exception(f"Error stopping recognition: {e}")
            # self.action_button.setText("语音输入")
            logger.info("Recognition stopped")

    def on_small_button_clicked(self):
        logger.info("Start index.html")
        webbrowser.open(f'file://{HTML_PATH}')

    

    def on_interrupt_clicked(self):
        logger.info("Interrupt button clicked")
        """处理打断按钮点击事件"""
        if self.check_audio_playing():
            # self.animation_state = "idle"  # 切换到待机状态
            # self.idle_index = 0
            # self.current_idle_frames = None
            # if is_connected():
                # if self.recognition_thread and self.recognition_thread.is_alive():
                #     try:
                #         self.recognition_thread.join(timeout=0.1)  # 设置较短的超时时间
                #     except Exception as e:
                #         print(f"停止语音识别时发生错误: {e}")
            self.is_interrupt = True
            if speech_lock.locked():
                speech_lock.release()
                th_online = threading.Thread(target=choose, args=(is_connected(), 'interrupt', self, ), daemon=True)
                th_online.start()
                self.animation_state = "idle"  # 切换到待机状态
                self.idle_index = 0
                self.current_idle_frames = None
            # else:
            #     # self.engine.endLoop()
            #     logger.info("no_connect")
            #     self.interrupt_flag = True
            #     self.clear_queue()
            #     self.engine.stop()
            #     # try:
            #     #     self.engine.endLoop()
            #     # except:
            #     #     print("loop not start")
            #     # del self.engine
            #     # self.engine = None
            #     th_offline = threading.Thread(target=choose, args=(is_connected(), 'interrupt', self, ), daemon=True)
            #     th_offline.start()
            #     th_offline.join(timeout=0.01)
                
            # # self.stop_recognition()
            # # 创建新线程来运行异步函数
        else:
            # 创建新线程来运行异步函数
            # threading.Thread(target=lambda: asyncio.run(speak_tone_no(self, '当前我没有说话')), daemon=True).start()
            th_no_speaking = threading.Thread(target=choose, args=(is_connected(), 'no_speak', self, ), daemon=True)
            th_no_speaking.start()
            th_no_speaking.join(timeout=0.01)

    def check_audio_playing(self):
        """检查是否有音频正在播放"""
        try:
            if is_connected():
                # 检查是否有音频正在播放
                if pygame.mixer.music.get_busy():
                    logger.info("Current audio is playing")
                    return True
                else:
                    logger.info("Current audio is not playing")
                    return False
            else:
                # 未联网时检查本地语音合成是否在朗读
                if self.engine.isBusy():
                    logger.info("Current audio is reading")
                    return True
                else:
                    logger.info("Current audio is not reading")
                    return False
        except Exception as e:
            logger.exception(f"Check audio status error: {e}")
            return False
        
    def clear_queue(self):
        """清空文本队列"""
        try:
            while not text_queue.empty():
                text_queue.get()
            logger.info("The queue is empty successfully")
        except Exception as e:
            logger.exception(f"Clear queue error:{e}")

    def close_all(self):
        logger.info("X button is clicked!")
        logger.info("Closing application")
        os.kill(os.getpid(), signal.SIGINT)

    def resizeEvent(self, event):
        """窗口大小变化时自动调整关闭按钮和气泡文本框位置"""
        super().resizeEvent(event)

        # # === 关闭按钮位置（右上角，留 5 像素边距） ===
        # button_size = self.close_button.size()
        # x = self.video_label.width() - button_size.width() - 5
        # self.close_button.move(x, 5)

        # === 文本框在按钮下方 ===
        button_bottom = self.action_button.y() + self.action_button.height()
        margin = 30  # 与按钮间距

        # 宽度占屏幕比例（比如 35%）
        bubble_width = self.video_label.width() * 0.2
        # 高度占屏幕高度比例（比如 12%）
        bubble_height = self.video_label.height() * 0.12

        # # 左上用户文本框
        self.scroll_area1.setGeometry(
            30,  # 左边固定 30px
            button_bottom + margin,
            bubble_width,
            bubble_height
        )
        # print(self.width() - bubble_width)
        # print(self.width())
        # print(bubble_width)

        # 右下模型文本框
        self.scroll_area.setGeometry(
            self.video_label.width() - bubble_width - 500,
            button_bottom + margin + bubble_height + 10,  # 模型框在用户框下方一点
            bubble_width,
            bubble_height
        )
        self.scroll_area.raise_()  # 确保滚动区域在最上层

    def load_scaled_icon(self, path, size):
        """加载并缩放图标"""
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            return QIcon(pixmap.scaled(
                size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
        return QIcon()

    def set_user_text(self, text: str):
        """设置用户对话文本"""
        self.user_text_requested.emit(text)

    @Slot(str)
    def _set_user_text(self, text: str):
        if len(text) > self.max_text_length:
            text = text[:self.max_text_length] + "..."
        self.user_text = text
        self.user_bubble.setText(text)  # 同步显示

    def set_model_text(self, text: str):
        """设置模型回答文本"""
        self.model_text_requested.emit(text)

    @Slot(str)
    def _set_model_text(self, text: str):
        # if len(text) > self.max_text_length:
        #     text = text[:self.max_text_length] + "..."
        self.model_text = text
        self.model_bubble.setText(text)  # 同步显示

    def clear_user_text(self):
        """清除用户对话文本。"""
        self.user_text_clear_requested.emit()

    @Slot()
    def _clear_user_text(self):
        self.user_text = ""
        self.user_bubble.clear()

    def clear_model_text(self):
        """清除模型回答文本。"""
        self.model_text_clear_requested.emit()

    @Slot()
    def _clear_model_text(self):
        self.model_text = ""
        self.model_bubble.clear()

    def clear_texts(self):
        """清除所有对话文本"""
        self.all_text_clear_requested.emit()

    @Slot()
    def _clear_texts(self):
        self.user_text = ""
        self.model_text = ""
        self.user_bubble.clear()
        self.model_bubble.clear()

    def set_recognition_icon(self, active: bool):
        """切换识别按钮图标，可从后台线程安全调用。"""
        self.recognition_icon_requested.emit(active)

    @Slot(bool)
    def _set_recognition_icon(self, active: bool):
        self.action_button.setIcon(self.active_icon if active else self.normal_icon)

    def showEvent(self, event):
        """窗口显示事件处理"""
        super().showEvent(event)
        # 在窗口显示后设置背景图片
        # print(self.left_panel.size())
        # print(self.left_panel.width())
        # print(self.left_panel.height())
        if hasattr(self, 'background_label'):
            self.background_label.setGeometry(0, 0, self.left_panel.width(), self.left_panel.height())
            self.background_label.setPixmap(QPixmap(BACKGROUND_IMAGE).scaled(self.left_panel.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))


class RotatingButtonsWidget(QWidget):
    def __init__(self, mainwindow, parent=None, radius_x=200, radius_y=350, num_buttons=8, button_radius=30):
        self.mainwindow = mainwindow
        # 计算宽高，确保按钮不被裁剪
        width = radius_x * 2 + button_radius * 2
        height = radius_y * 2 + button_radius * 2
        super().__init__(parent)
        self.setFixedSize(width, height)

        # 默认中心在组件中心
        self.center_x = width / 2
        self.center_y = height / 2
        self.radius_x = radius_x
        self.radius_y = radius_y
        self.button_radius = button_radius
        self.num_buttons = num_buttons
        self.buttons = []
        self.angles = []
        self.paused = False

        # 创建按钮并安装事件过滤器
        for i in range(self.num_buttons):
            angle = (2 * math.pi * i) / self.num_buttons
            x = self.center_x + self.radius_x * math.cos(angle)
            y = self.center_y + self.radius_y * math.sin(angle)
            btn = QPushButton(str(i+1), self)
            btn.setGeometry(int(x - self.button_radius), int(y - self.button_radius),
                            self.button_radius * 2, self.button_radius * 2)
            btn.setStyleSheet(
                f"""
                QPushButton {{ background-color: rgb(166, 27, 41); color: white; border-radius: {self.button_radius}px; font-size: 20px; }}
                QPushButton:hover {{ background-color: rgb(130, 17, 31); }}
                QPushButton:pressed {{ background-color: rgb(75, 30, 47); }}
                """
            )
            # 设置工具提示
            category = self.mainwindow.category_map[i+1]
            items = self.mainwindow.category_items_map[category][:6]
            tooltip_text = f"{category}\n\n其中部分非遗文化如下\n\n" + "\n".join([item for item in items if item])
            btn.setToolTip(tooltip_text)
            btn.clicked.connect(lambda checked, num=i+1: self.button_clicked(num))
            btn.installEventFilter(self)
            self.buttons.append(btn)
            self.angles.append(angle)

        # 定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate_buttons)
        self.timer.start(50)

    def rotate_buttons(self):
        if self.paused:
            return
        speed = 0.01
        for i, btn in enumerate(self.buttons):
            angle = self.angles[i] + speed
            self.angles[i] = angle
            x = self.center_x + self.radius_x * math.cos(angle)
            y = self.center_y + self.radius_y * math.sin(angle)
            btn.move(int(x - self.button_radius), int(y - self.button_radius))

    def button_clicked(self, num):
        # 或者更精确的方式（推荐）：
        for i in reversed(range(self.mainwindow.text_layout.count())):
            widget = self.mainwindow.text_layout.itemAt(i).widget()
            if isinstance(widget, QLabel):
                widget.deleteLater()

        # 然后重新设置滚动区域（确保 UI 更新）
        self.mainwindow.text_scroll_area.update()
        # print(self.mainwindow.front_button)
        if self.mainwindow.front_button != num:
            text = f"按钮 {num} 被点击了！"
            # 计算尺寸
            label_width = int(self.mainwindow.rotating_width * 0.5)
            label_height = int(self.mainwindow.rotating_height * 0.05)
            # 添加标签
            nums = self.mainwindow.category_map[num]
            titles = self.mainwindow.category_items_map[nums]

            for title in set(titles):
                if title == '':
                    continue
                label = QLabel()
                label.setStyleSheet("""
                                    QLabel {
                                        background: rgba(30, 30, 30, 0.7);
                                        color: white;
                                        font-size: 24px;
                                        font-weight: bold;
                                        border-radius: 10px;
                                        padding: 10px 10px;
                                    }
                                    QLabel:hover {
                                        background: rgba(50, 50, 50, 0.8);
                                        background-color: rgb(130, 17, 31);
                                    }
                                    """)
                label.setText(title)
                label.setAlignment(Qt.AlignLeft)
                label.setFixedSize(label_width, label_height)
                # 添加悬停提示
                label.setToolTip(str(get_summary().get(title, "")))
                # 安装事件过滤器以处理鼠标悬停事件
                label.installEventFilter(self)
                self.mainwindow.text_layout.addWidget(label)
        else:
            label_width, label_height = int(self.mainwindow.rotating_width * 0.5), int(self.mainwindow.rotating_height * 0.6)
            label = QLabel(self.mainwindow.text_overlay_container)
            label.setStyleSheet("""
                                QLabel {
                                    background: rgba(30, 30, 30, 0.7);
                                    color: white;
                                    font-size: 24px;
                                    font-weight: bold;
                                    border-radius: 10px;
                                    padding: 5px 5px;
                                }
                                QLabel:hover {
                                    background: rgba(50, 50, 50, 0.8);
                                }
                                """)
            label.setText('\n\n'.join([f'{i}: {value}' for i, value in (self.mainwindow.category_map.items())]))
            label.setAlignment(Qt.AlignLeft)
            label.setFixedSize(label_width, label_height)
            # 添加悬停提示
            label.setToolTip("点击任意类别查看详细信息")
            # 安装事件过滤器以处理鼠标悬停事件
            label.installEventFilter(self)
            self.mainwindow.text_layout.addWidget(label)

        self.mainwindow.front_button = num

    def eventFilter(self, watched, event):
        if watched in self.buttons:
            if event.type() == QEvent.Enter:
                self.paused = True
            elif event.type() == QEvent.Leave:
                self.paused = False
        elif isinstance(watched, QLabel):
            if event.type() == QEvent.Enter:
                # 当鼠标进入标签时，可以添加额外的视觉效果
                watched.setStyleSheet(watched.styleSheet().replace("rgba(30, 30, 30, 0.7)", "rgba(50, 50, 50, 0.8)"))
            elif event.type() == QEvent.Leave:
                # 当鼠标离开标签时，恢复原始样式
                watched.setStyleSheet(watched.styleSheet().replace("rgba(50, 50, 50, 0.8)", "rgba(30, 30, 30, 0.7)"))
        return super().eventFilter(watched, event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))

