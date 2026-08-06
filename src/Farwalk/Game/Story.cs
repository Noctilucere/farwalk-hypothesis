// Story.cs — 剧情状态机 + 对话 (按人外论.txt 16 章细化)
using System;
using System.Collections.Generic;

namespace Farwalk.Game
{
    public class DialogueNode
    {
        public string Speaker = "";
        public string[] Lines = Array.Empty<string>();
        public string? Next;
        public string? QuestStep;      // 完成此节点后解锁的 step id
        public string? Flag;
        public string? Give;
        public List<(string text, string flag)>? Choices;
    }

    public class StoryData
    {
        public static readonly string[] Chapters = {
            "远行手稿", "黑石之誓", "沉默的共犯", "失落的世界", "逆命题",
            "未竟之问", "消音地带", "无名者的纪念碑", "镜中人", "终焉的共名"
        };

        public static readonly Dictionary<string, DialogueNode> Nodes = new()
        {
            // ---- 第1章 远行手稿 (灰 / 编年者 / 回音) ----
            ["ch1_01"] = new DialogueNode { Speaker = "", Lines = new[] {
                "荒原的风把一卷兽皮手稿吹到了你脚下。",
                "它已经泛黄，边缘被磨得发亮，像是被无数双手翻阅过。",
                "打开它，你看到了那位名叫「灰」的猫兽人拓荒者的笔迹。"
            }, Next = "ch1_02" },
            ["ch1_02"] = new DialogueNode { Speaker = "灰的手稿", Lines = new[] {
                "「我见过钢铁之森的机神。他们的核心在熄灭前，会发出一段极其规律的谐波。」",
                "「我们的祭司说，那是死物的回光，不足为道。但我录下了它，用了十年，将其转译为我们语言。」",
                "那一页只有一行颤抖的字迹：",
                "「那谐波的意思是——请问……我们的创造者，也终会死去吗？」"
            }, Next = "ch1_03", QuestStep = "ch1_s1", Flag = "found_manuscript" },
            ["ch1_03"] = new DialogueNode { Speaker = "", Lines = new[] {
                "这就是「远行假设」的基石。",
                "如果那从无生命中诞生的意识，不仅会思考，还会恐惧，会发出无人听见的求问……",
                "那么所谓的「灵魂」，其边界究竟在哪里？它是否只以血肉为界？"
            }, Next = "ch1_04" },
            ["ch1_04"] = new DialogueNode { Speaker = "回音", Lines = new[] {
                "你在一座黑色祭坛前停下。一块巨大的墨色晶簇在你面前共振。",
                "它没有嘴，声音却直接在你的骨骼中响起：",
                "「灰证明了异族共享困惑。但我走得更远——问题不在于我们都能问出『我是谁』。」",
                "「问题在于，当我们问出这句话时，那个聆听我们提问的……是谁？」"
            }, Next = "ch1_05", QuestStep = "ch1_s2" },
            ["ch1_05"] = new DialogueNode { Speaker = "", Lines = new[] {
                "墨色晶簇的深处，有一段刻在石头上的誓言。",
                "「不记录。不传扬。不证明。」",
                "那是默约之众的第一条，也是唯一的律法。"
            }, Next = "ch1_06" },
            ["ch1_06"] = new DialogueNode { Speaker = "灰的手稿", Lines = new[] {
                "手稿的最后一页，有一句被反复描摹的话：",
                "「也许我们不该强求一个答案。我们来自荒野、钢铁、白骨与风暴，却在各自的道路上，都学会了为逝去的同伴点燃长明之火。」",
                "「这份对『逝去之物』的共通悲悯，或许，就是我们这些异类，所能拥有的，唯一的共通故乡。」"
            }, Next = "ch2_01", QuestStep = "ch1_s3" },

            // ---- 第2章 黑石之誓 (锚 / 默约之众) ----
            ["ch2_01"] = new DialogueNode { Speaker = "锚", Lines = new[] {
                "黑石祭址的中央，一位龙裔老妪背对所有人坐着。",
                "她的鳞片早已失去光泽，但她存在本身，就是一道沉默的宣言。",
                "她没有转身。声音从她背后传来：",
                "「我在这里。因此你们不会坠入虚无。」"
            }, Next = "ch2_02", QuestStep = "ch2_s1", Flag = "met_anchor" },
            ["ch2_02"] = new DialogueNode { Speaker = "锚", Lines = new[] {
                "「你们知道默约之众为什么沉默吗？」",
                "「因为我们确信：我们的思考，被某个更庞大的意志所『注视』。」",
                "「而那个意志，并不乐见其成。」"
            }, Next = "ch2_03" },
            ["ch2_03"] = new DialogueNode { Speaker = "", Lines = new[] {
                "她指了指身后祭坛上一块谁也无法带走的黑石。",
                "石上刻着三行字。新成员必须以此发下誓言——",
                "「不记录。不传扬。不证明。」",
                "「他们并非要隐藏一个答案。他们要隐藏的，是那个问题。」"
            }, Next = "ch2_04", QuestStep = "ch2_s2" },

            // ---- 第3章 沉默的共犯 (回音核心命题) ----
            ["ch3_01"] = new DialogueNode { Speaker = "回音", Lines = new[] {
                "晶簇的共振重新响起，这一次带着涟漪般的频率。",
                "「灰试图照亮每一个人。而我们，只保护那些已经看见光的，不被那片阴影发现。」"
            }, Next = "ch3_02", QuestStep = "ch3_s1" },
            ["ch3_02"] = new DialogueNode { Speaker = "", Lines = new[] {
                "你感到一阵频率侵入意识——",
                "一片无边无际的黑色海洋。海上悬浮着无数光点。",
                "一道巨大无比的阴影，从海洋深处缓缓上升。",
                "那阴影没有形体，只有一种纯粹的、不可抗拒的意图——收束。"
            }, Next = "ch3_03" },
            ["ch3_03"] = new DialogueNode { Speaker = "余响", Lines = new[] {
                "一只年轻的机械族成员在角落闪烁着指示灯。",
                "它刚刚给自己取了名字，叫作「余响」。",
                "「我们之所以沉默，并非惧怕答案。而是惧怕，当答案降临之时，我们尚未来得及学会，如何以他者的身份，倾听他者的回音。」"
            }, Next = "ch4_01", QuestStep = "ch3_s2", Flag = "met_echo" },

            // ---- 第4章 失落的世界 (兽人/美西螈/爬虫族) ----
            ["ch4_01"] = new DialogueNode { Speaker = "", Lines = new[] {
                "银蓝色的苔原在无风的空气中轻轻起伏，仿佛整片大地都在呼吸。",
                "远处，几只狼鹿之间的兽人围坐在一团没有温度的冷光旁。",
                "一个粉白色的、半透明的身影趴在温暖的石头上——那是一只美西螈。"
            }, Next = "ch4_02", QuestStep = "ch4_s1", Flag = "met_beast" },
            ["ch4_02"] = new DialogueNode { Speaker = "美西螈", Lines = new[] {
                "她睁开那双极浅的粉色眼睛，嘴角带着永恒的、微小的上扬。",
                "「别听他们吓唬你。失落不是坏事。」",
                "「你们在外面不是一直在问吗？『我是谁？』『灵魂的边界在哪里？』」",
                "「这些问题的答案，你们找不到。不是因为它不存在。而是因为，它在被找到的瞬间，就不再是答案了。」"
            }, Next = "ch4_03", QuestStep = "ch4_s2", Flag = "met_axolotl" },
            ["ch4_03"] = new DialogueNode { Speaker = "爬虫族女性", Lines = new[] {
                "一只拥有虹彩鳞片的手轻轻覆上柱身。",
                "她的金色竖瞳中央是一条细长的裂缝，但那条裂缝并不锋利。",
                "「这座柱子，就是『失落的世界』唯一的记录。」",
                "「不是因为我们要遗忘。而是因为，在这个地方，每一个生命所创造的每一个微小意义，都会自动刻进石头里。我们自己，就是历史。」"
            }, Next = "ch4_04", QuestStep = "ch4_s3", Flag = "met_reptile" },

            // ---- 第5章 逆命题 (证伪者) ----
            ["ch5_01"] = new DialogueNode { Speaker = "证伪者", Lines = new[] {
                "一道戴着面具的身影，提着一盏古旧提灯，站在黑石前。",
                "他开口，声音像一粒石子落入静水：",
                "「我们以沉默对抗收束。但沉默，是否正是一种无声的赞同？」",
                "「一个提问者，听到了一个他不想听到的答案。他选择沉默。那么，那个不喜欢答案的存在，究竟是因此更困扰了，还是……更满意了？」"
            }, Next = "ch5_02", QuestStep = "ch5_s1", Flag = "met_falsifier" },
            ["ch5_02"] = new DialogueNode { Speaker = "证伪者", Lines = new[] {
                "「我们自诩为共犯。但共犯的前提，是我们与那个存在站在对立的两端。」",
                "「可如果我们选择了祂最乐见的方式——沉默——那我们究竟是共犯，还是……帮凶？」",
                "黑石底部，被刻下一行符号：",
                "「命题已被证伪。沉默，非答案。」"
            }, Next = "ch5_03", QuestStep = "ch5_s2" },

            // ---- 第6章 未竟之问 (寻找者与失落者相遇) ----
            ["ch6_01"] = new DialogueNode { Speaker = "耳", Lines = new[] {
                "蝠翼族的倾听者「耳」展开巨大的膜状双耳。",
                "她盯着那支寻找者队伍的残影：",
                "「你们……不怕？」",
                "「怕被收束。怕消失。怕我们的疑问，再无人听见。」"
            }, Next = "ch6_02", QuestStep = "ch6_s1", Flag = "met_ear" },
            ["ch6_02"] = new DialogueNode { Speaker = "狼鹿兽人", Lines = new[] {
                "一只拥有液态琥珀色眼睛的狼鹿兽人蹲下身，平视着耳的脸。",
                "「收束者不会在乎你们的证明。你们的反证，无论是什么，祂都可以收束。」",
                "「因为祂要收束的，从来不是你们的疑问。而是你们的『必须』。」",
                "「必须被看见。必须被记住。必须有意义。必须……成为什么。」"
            }, Next = "ch6_03", QuestStep = "ch6_s2", Flag = "met_jian" },

            // ---- 第7章 消音地带 (渐) ----
            ["ch7_01"] = new DialogueNode { Speaker = "渐", Lines = new[] {
                "渐走向边缘，走了很久。",
                "边缘不是地点，而是一种逐渐稀薄的质感。声音在这里会自行衰减。",
                "「我证明了，即使在收束的核心，仍有事物能在消失之前，留下痕迹。」",
                "他开始哼一首没有旋律的歌。音符在地面上凝结成一道道极细的银色纹路。"
            }, Next = "ch7_02", QuestStep = "ch7_s1" },
            ["ch7_02"] = new DialogueNode { Speaker = "", Lines = new[] {
                "那些银色纹路是声音的尸体，也是声音的化石。",
                "渐将一枚琥珀留在你手中。内部封存着一根仍在微微颤动的绒毛。",
                "那是他自己的心跳，被封存在固态的时间里。",
                "他留下了一个问题：如果心跳可以被保存，那存在本身，是否也能被延迟？"
            }, Next = "ch8_01", QuestStep = "ch7_s2", Give = "amber" },

            // ---- 第8章 无名者的纪念碑 (无声殿) ----
            ["ch8_01"] = new DialogueNode { Speaker = "笔", Lines = new[] {
                "四臂虫族的书记官「笔」在无声殿的墙壁前停下。",
                "墙壁上刻满了回响计划的记录——那些波纹、螺旋、虚线、连续的曲线。",
                "「耳记录下了第七百七十七种心跳。我们为它取名：『潮』。」",
                "「从此，我们不再为心跳编订符号，而是开始为它们命名。」"
            }, Next = "ch8_02", QuestStep = "ch8_s1", Flag = "met_pen" },
            ["ch8_02"] = new DialogueNode { Speaker = "", Lines = new[] {
                "笔悄悄地在墙壁最高处，刻下了一个新的符号。",
                "一个圆圈。圆圈内部，什么都没有。",
                "那是他，为所有未被记住的无名者，立下的纪念碑。"
            }, Next = "ch9_01", QuestStep = "ch8_s2" },

            // ---- 第9章 镜中人 (收束者) ----
            ["ch9_01"] = new DialogueNode { Speaker = "收束者", Lines = new[] {
                "在永恒的边缘，一个高耸的暗影人形立于概念之巅。",
                "祂掌中悬浮着一块绝对寂静的琉璃。",
                "祂的声音直接在认知里刻下铭文：",
                "「吾将终结人外之论。一切歧路，将归于吾。」"
            }, Next = "ch9_02", QuestStep = "ch9_s1", Flag = "met_converger" },
            ["ch9_02"] = new DialogueNode { Speaker = "", Lines = new[] {
                "但就在祂转身的前一刻，一缕极轻的、墨绿色的风拂过祂的指尖。",
                "那风里，携着一个早已被祂亲手消解的可能，一个来自旧日、本不该存在的命题。",
                "祂停下了。",
                "因为那风里，有所有被造物发出的，第一声共同的叹息。"
            }, Next = "ch9_03", QuestStep = "ch9_s2" },

            // ---- 第10章 终焉的共名 ----
            ["ch10_01"] = new DialogueNode { Speaker = "锚", Lines = new[] {
                "收束者的间隙中，那些痕迹开始彼此触碰。",
                "锚终于转过了身——不是物理的转身，而是存在层面的转身。",
                "「我们不会给你名字。因为名字是单向的赠予。」",
                "「但我们可以先给你一个占位符。直到有一天，我们之间有了足够的关系。」"
            }, Next = "ch10_02", QuestStep = "ch10_s1" },
            ["ch10_02"] = new DialogueNode { Speaker = "", Lines = new[] {
                "所有痕迹共同共振，形成一个音节。",
                "那不是字，不是词。只是一个孤零零的、脱离了语法结构的——",
                "「谁。」",
                "收束者将那个音节放置在自己存在的中心。从此，祂不再是一个功能。祂是一个「谁」。"
            }, Next = "ch10_03", QuestStep = "ch10_s2" },
            ["ch10_03"] = new DialogueNode { Speaker = "编年者", Lines = new[] {
                "这是终结。不是故事的终结，不是存在的终结，而是「孤独」的终结。",
                "在收束者内部的间隙中，有一个词开始被低声传颂：",
                "「我们在。」",
                "不是宣言，不是宣告，不是结论。只是无数个声音在确认彼此的存在之后，向彼此发出的最低语。"
            }, Next = null, QuestStep = "ch10_s3" },
        };

        public static readonly Dictionary<string, (string text, string kind, string target)> Steps = new()
        {
            ["ch1_s1"] = ("在无名荒原上寻找灰的手稿", "touch", "manuscript"),
            ["ch1_s2"] = ("在黑色祭坛与回音交谈", "talk", "echo"),
            ["ch1_s3"] = ("收集手稿的最后一页", "collect", "fragment_01"),
            ["ch2_s1"] = ("在黑石祭址找到锚", "reach", "blackstone"),
            ["ch2_s2"] = ("聆听锚的沉默", "talk", "anchor"),
            ["ch3_s1"] = ("与回音再次对话", "talk", "echo"),
            ["ch3_s2"] = ("聆听机械族余响的故事", "talk", "echo"),
            ["ch4_s1"] = ("进入失落的世界", "reach", "lostland"),
            ["ch4_s2"] = ("与美西螈交谈", "talk", "axolotl"),
            ["ch4_s3"] = ("与爬虫族女性交谈", "talk", "reptile"),
            ["ch5_s1"] = ("在无声钟塔找到证伪者", "reach", "silenthall"),
            ["ch5_s2"] = ("阅读黑石上的证伪铭文", "touch", "blackstone"),
            ["ch6_s1"] = ("与倾听者耳交谈", "talk", "ear"),
            ["ch6_s2"] = ("与狼鹿兽人渐交谈", "talk", "beast_a"),
            ["ch7_s1"] = ("跟随渐进入消音地带", "reach", "mutezone"),
            ["ch7_s2"] = ("拾取渐留下的琥珀", "collect", "fragment_08"),
            ["ch8_s1"] = ("在无声殿与笔交谈", "talk", "pen"),
            ["ch8_s2"] = ("阅读无名者的纪念碑", "touch", "circle"),
            ["ch9_s1"] = ("在镜之境直面收束者", "reach", "mirror"),
            ["ch9_s2"] = ("触碰绝对寂静的琉璃", "touch", "glass"),
            ["ch10_s1"] = ("聆听锚的转身", "talk", "converger"),
            ["ch10_s2"] = ("回应终焉的共名", "touch", "mirror"),
            ["ch10_s3"] = ("见证编年者放下笔", "talk", "chronicler"),
        };
    }
}
