# ruff: noqa: E501
"""Seed a clean live demo: Jujutsu Kaisen-inspired draft with a wiki.

    cd backend && uv run python -m scripts.seed_jjk_demo

The prose is original fan-fiction summary written for this fixture. It is not
copied from the manga. The final chapter deliberately breaks continuity.
"""

import asyncio

from app.db import async_session
from app.models import Arc, Chapter, Story, User
from app.schemas.wiki import EventCreate, FactCreate, RelationshipCreate, ThreadCreate
from app.security import get_password_hash
from app.services.entities import create_entity, extract_mentions
from app.services.facts import create_fact, create_relationship
from app.services.threads import create_event, create_thread

EMAIL = "demo@stillroom.local"
USERNAME = "demo"
PASSWORD = "correct horse battery"
STORY_TITLE = "Jujutsu Kaisen: The First Finger"

CHAPTERS = [
    (
        "Ryomen Sukuna",
        """The Occult Club at Sugisawa High had one rule: do not open the box.

Yuji Itadori broke the rule because his friends were bored. Inside the box was a dried finger wrapped in seals, and inside the finger was something that had been waiting a very long time. Ryomen Sukuna, the king of curses, had been reduced to twenty mummified pieces. The club had found one.

That night, Yuji's grandfather died in the hospital. His last words were not kind. "You are strong," he said. "Use it on other people." Yuji did not know yet that the sentence would become a job description.

Megumi Fushiguro arrived at the school looking for the finger. He found a boy with impossible strength, a curse eating the Occult Club, and no clean way to explain any of it. Yuji punched the curse through a wall. Megumi called him an idiot and told him to run.

Yuji swallowed the finger instead. He did not plan to. The curse had his friend by the throat, and the finger was the only thing in reach. Sukuna took control for eleven seconds. When Yuji woke up, the curse was gone, the building was damaged, and Satoru Gojo was standing over him with a smile that did not reach his eyes.

"Congratulations," Gojo said. "You are a vessel. The higher-ups at Tokyo Jujutsu High will want to execute you. I would rather not let them."

Yuji looked at his hands. They were shaking. Somewhere behind his ribs, Sukuna laughed and told him he would enjoy watching the boy learn what a curse really was. In Sendai, the rain kept falling on a school that no longer had an Occult Club.""",
    ),
    (
        "For Myself",
        """Tokyo Jujutsu High was a school built inside a mountain and a lie.

Gojo walked Yuji through the courtyard as if the death sentence hanging over him were a scheduling problem. Principal Masamichi Yaga questioned Yuji for an hour. Shoko Ieiri checked his vitals and told him he should be dead. The higher-ups wanted him sealed, studied, and then killed. Gojo proposed a compromise: Yuji would eat every remaining finger, become a complete vessel, and then die on the school's terms.

"That is the deal," Gojo said. "You get to choose how you spend the time between now and the end."

Yuji chose training. Megumi watched from the edge of the field and pretended not to care. The cursed energy in Yuji's body did not behave like a student's. It moved in sudden, blunt surges, as if it had been borrowed from a much larger animal. Gojo taught him to wrap his fists, to breathe, and to stop apologizing for the space he took up.

At night, Yuji sat on the dorm roof and thought about his grandfather. He had spent his whole life being useful in small ways: carrying boxes, helping strangers, keeping the club from falling apart. Now usefulness had a body count. He could save people, or he could be the person everyone else needed to save.

Sukuna spoke from the dark behind his eyes. "You are not a hero. You are a coffin with a heartbeat."

Yuji answered, "Then I will be a good coffin."

It was not a plan. It was the first thing he had ever chosen for himself.""",
    ),
    (
        "Girl of Steel",
        """Nobara Kugisaki arrived in Tokyo with three bags, a hammer, and no intention of being impressed.

She met Yuji and Megumi at a station where a curse had nested inside the lost-and-found. The assignment was supposed to be simple. It was not. The curse had learned to wear the station's announcements like a voice, and every time it spoke, a commuter walked toward the tracks.

Nobara did not wait for a plan. She drew a nail, struck it with her hammer, and pinned the curse's shadow to the floor. The technique was called Straw Doll. It was precise, ugly, and entirely hers.

"You two can stand there looking serious," she said. "I am going to finish my shopping."

Yuji decided he liked her immediately. Megumi decided she was a liability and then revised the opinion twice before lunch. Together they cleared the station, saved the commuters, and made it back to school in time for Nobara to complain about the cafeteria.

That night, Gojo told them they would be a team. Nobara said she worked alone. Yuji said he did not mind carrying things. Megumi said nothing, which was how he agreed to most things.

In her room, Nobara unwrapped a photograph of a village street and set it beside her hammer. She had left home to prove that a girl from the country could become someone the city remembered. The photo stayed face down. The hammer stayed within reach.""",
    ),
    (
        "Curse Womb Must Die",
        """The detention center had been closed for years, but the curse inside it had been growing.

Gojo assigned the first-years to investigate. Megumi brought his Divine Dogs. Nobara brought enough nails to rebuild a roof. Yuji brought the finger he had swallowed and the uneasy feeling that it was listening.

The building had no real rooms anymore. Its corridors folded back into themselves. A veil had been drawn over the site, cutting off the sky and the signal on their phones. Megumi recognized the work of a special-grade curse. He told the others to retreat. The exit was already gone.

The curse was a womb of flesh and mouths, a thing that had never been a person and had learned to imitate one. It called Yuji by name. It said Sukuna was waiting. It split the corridors open and poured lesser curses through the gaps.

Nobara held the west hall. Megumi sent his dogs into the dark and did not let himself count how many came back. Yuji pushed forward alone. He could hear a child crying somewhere below the floor, and he could not make himself walk away from it.

That was the problem with being strong. There was always a door that only you could open, and someone behind it who would die if you did not.

When the floor gave way, Yuji fell into the lowest chamber. The crying stopped. A voice that was not his own said, "Finally."

Above him, the veil thickened. Tokyo Jujutsu High lost contact with all three students at 11:42 p.m.""",
    ),
    (
        "Curse Womb Must Die II",
        """Megumi found Yuji at the bottom of the detention center with his chest open.

The special-grade curse had done its work. Yuji was not breathing. Megumi did not have time to grieve. The curse was still moving, and the only thing between it and Nobara was a half-trained sorcerer with two exhausted shikigami.

Then Sukuna woke up.

Yuji's body rearranged itself around the king of curses. Black lines spread across his arms. A second pair of eyes opened beneath the first. Sukuna looked at the curse, then at Megumi, then at the ceiling, and smiled like a man returning to a house he had missed.

The fight lasted less than a minute. It was not a battle. It was a correction. When the curse was gone, Sukuna turned to Megumi and asked what the boy wanted to do with the rest of his life.

Megumi, bleeding, said, "Give him back."

Sukuna laughed. "He is already dead."

But Yuji was not fully gone. He clawed his way back through the dark and made a bargain he did not understand: Sukuna would heal the body, and Yuji would owe him one favor. The wording mattered. The king of curses chose the words carefully.

Yuji woke in a hospital bed three days later. Ieiri said his heart had stopped for four minutes. Gojo said the higher-ups were calling it a miracle. Megumi said nothing. Nobara hit Yuji on the shoulder and told him never to do that again.

In the mirror, Yuji saw black lines fading from his skin. Sukuna's voice was very quiet. "One favor," it said. "I will collect."

Outside, the rain had stopped. It did not make anything feel cleaner.""",
    ),
    (
        "After Rain",
        """Yuji was given a week of leave and no instructions on how to use it.

He went to the movies. It was the only thing he could think of that did not involve curses, funerals, or the sound of his own heart stopping. The theater was almost empty. A boy in a school uniform sat two rows down with a bucket of popcorn and a face that looked permanently braced for bad news.

The boy was Junpei Yoshino. He liked horror films because the monsters were honest. He liked the dark because no one could see him flinch. Yuji sat beside him and discovered that they both hated the ending.

They met again the next day. Junpei showed him a movie about a man who could not die. Yuji showed him a scar that had not been there a month ago and lied about where it came from. For a few hours, they were just two teenagers arguing about a director.

At school, Junpei was being crushed slowly. His classmates had turned cruelty into a daily chore. His mother, Nagi, was the only person who still touched him without flinching. Yuji did not know any of this yet. He only knew that Junpei was easier to talk to than most people at Jujutsu High.

In the shadows of the cinema, a pale figure watched them both. Mahito had no interest in the movie. He was interested in the shape of a lonely boy's soul and how much pressure it would take before it changed.

Mahito introduced himself to Junpei after the credits. He said all the right things. He said the people who hurt Junpei were the real curses. He said Junpei could become something that never had to be afraid again.

Junpei listened. In his pocket, his phone buzzed with a message from his mother. He did not answer it.""",
    ),
    (
        "Assault",
        """Junpei's school had a boiler room that nobody used and a social order that everyone understood.

He was not at the bottom. The boys who beat him were careful about that. They left marks where his uniform could hide them and invited him to sit with them afterward, so that no teacher could say he was excluded. Junpei had learned to smile at the exact moment the door closed.

Mahito offered him a way out. It was not a weapon at first. It was a question: if you could reshape any part of yourself, what would you change?

Junpei started with his hands. Then his face. Then the part of him that flinched. Mahito watched each change with the patient delight of a child pulling wings off an insect. The cursed energy in Junpei's body was small, but it was his. No one had ever given him something that was his.

Yuji found Junpei outside the cinema after school. Junpei was different. His smile arrived late and stayed too long. He said he had a new friend. He said he was finally going to solve his own problems.

Yuji asked if he wanted to see a movie. Junpei said he had somewhere to be.

At Jujutsu High, Nanami Kento read the report on the detention center and underlined the same sentence three times. Two students, one special-grade curse, one vessel who should be dead. He did not like the pattern. He requested the Junpei Yoshino case before the higher-ups could bury it.

That night, a school window shattered. The boys who had made Junpei's life small went looking for him. They did not come back. The boiler room was warm, and something inside it was learning to breathe.""",
    ),
    (
        "That Place",
        """Nagi Yoshino came home from work to find her son sitting in the dark.

Junpei had not turned on any lights. He had not eaten. He was holding a film ticket and looking at the wall as if it had asked him a difficult question. Nagi sat beside him and put her hand on his shoulder. He did not pull away.

"You can tell me," she said. "Whatever it is."

They had always been a small family, two people against a city that did not notice them. Nagi worked double shifts. Junpei made dinner and pretended he had already eaten. It was not a happy life, but it was theirs.

Mahito was waiting outside.

He did not come in through the door. He came through the wall, smiling, and asked Junpei whether he was ready to stop being afraid. Nagi stood up. She told him to leave. She put herself between the curse and her son, which was the bravest thing she had ever done and the last.

Idle Transfiguration touched her once. Her body became a shape that had never been meant to hold a person. Junpei screamed. Mahito told him this was the lesson: love was just another thing that could be taken apart.

Junpei ran. He did not run to the police or to the school. He ran to Yuji.

Yuji was in the dormitory when his phone lit up. Junpei's voice on the other end was barely recognizable. "She is dead," he said. "The thing that did it is still there. I want to kill it."

Yuji grabbed his jacket. Nanami grabbed his wrist. "You are not going alone," the older sorcerer said.

They arrived at the Yoshino apartment to find the door open, the lights off, and a trail of cursed energy leading into the dark.""",
    ),
    (
        "Small Fry and Reverse Retribution",
        """Nanami Kento did not believe in heroic entrances. He believed in overtime, accurate paperwork, and hitting a curse where it was weakest.

He and Yuji followed Junpei's trail through the apartment block. Mahito had left the place open like a stage. The walls were soft where he had touched them. The television was still on, playing a documentary about deep-sea fish. In the bedroom, Nagi Yoshino's body had stopped moving.

Yuji could not look at her for long. Junpei was crouched in the corner with his hands over his ears.

Mahito appeared at the window. He told Junpei that humans were afraid of him because he was honest. He told Yuji that Sukuna was the only one who had ever been truthful with either of them. He offered Junpei a place in a world where no one would ever be powerless again.

Junpei looked at Yuji. For a moment, the boy from the cinema was still there, frightened and furious and fifteen.

Then Mahito reached out and changed him.

The fight that followed was not clean. Nanami's Ratio Technique found the seams in Mahito's body and cut them open. Yuji hit harder than he had ever hit anything. Mahito laughed through a mouth that kept moving. He said the best part was that Yuji had brought the boy to him.

Junpei did not survive the transformation. His body folded in on itself before Yuji could reach him. Mahito escaped through the wall, leaving a hole that looked like a wound.

Nanami put a hand on Yuji's back. It was not comfort. It was a reminder that they were still in a building with a civilian's body and a curse's trail and a report that had to be filed before morning.

"We go home," Nanami said.

Yuji did not cry until the train. Then he cried without making a sound, while the city lights slid past the window and Sukuna whispered that he had warned him.""",
    ),
    (
        "Idle Transfiguration",
        """Mahito was waiting for them in the sewer beneath the apartment block.

He had chosen the place carefully. It was dark, narrow, and full of water. Nanami could not use his full reach. Yuji could not see the curse coming until it was already touching him.

Mahito wanted Yuji to hate him. Hatred made souls easier to reshape. He talked about Junpei, about Nagi, about the boys in the boiler room. He said the world was a machine that turned people into tools, and he was the only one honest enough to show them the gears.

Yuji stopped listening. He stopped thinking about the right way to fight and started thinking about the next second. The next breath. The next hit.

Black Flash arrived without warning. The air folded. The curse's body opened. For one instant, Yuji understood what Gojo had meant about cursed energy: it was not a tool you picked up. It was a current you had to survive.

Nanami drove Mahito back. Yuji hit him again. The sewer shook. Somewhere above them, a train passed through the dark.

Mahito escaped. He was smiling, but he left a piece of himself behind.

When they climbed out, the city was quiet. Nanami took out his phone and called the school. Ieiri answered. Gojo, she said, had been killed during the detention-center operation. The veil had collapsed on him. There had been no body.

Yuji sat down on the curb. He had known Gojo for less than a month. It felt like losing a roof.

Nanami asked if he wanted to go back to Sendai. Yuji said no. He said he wanted to keep working. He said he wanted to be useful.

The word tasted different now. It tasted like something Sukuna had said it would.""",
    ),
    (
        "The Morning After",
        """Sunlight came through the dormitory window at eight in the morning. Yuji Itadori was seventeen years old, alive, and very hungry.

He had slept through his alarm. On the desk was a half-eaten bag of chips and a finished report. In the kitchen, Nobara Kugisaki was making coffee. Her hair was black and cropped short. She told Yuji he looked like a ghost and handed him a cup.

The common room was full. Megumi sat by the window with both Divine Dogs at his feet. Both dogs were white. Maki Zenin argued with Panda about training times. Toge Inumaki stood at the stove, carefully burning an egg.

And Satoru Gojo was sitting at the table, alive, drinking coffee through a straw because he refused to take the blindfold off inside.

"Morning," Gojo said. "I heard you had a rough week."

Yuji stared at him. "You died."

"Reports of my death were exaggerated." Gojo waved a hand. "The veil collapsed. I was in Kyoto, not Tokyo. Paperwork."

Yuji did not remember a Kyoto operation. He did not remember Gojo being anywhere but under the detention center. His head hurt when he tried to place the memory.

Junpei Yoshino came in from the balcony with a tray of rice. He was alive, his face unscarred, his hands steady. He said good morning to Yuji and asked whether they were still going to the movies on Saturday.

Yuji said yes. His mouth moved before the rest of him could catch up.

Nobara set a sword on the table instead of her hammer. She said the hammer was too loud for indoor work. No one corrected her. On the wall, the calendar said there were twenty-one Sukuna fingers in the world. Yuji counted the one inside himself and felt, for no reason he could name, that the number was wrong.

Outside, the city went on being a city. Inside, everyone ate breakfast and pretended the story made sense. Sukuna, quiet behind Yuji's ribs, began to laugh.""",
    ),
]


async def seed() -> None:
    async with async_session() as session:
        user = User(
            username=USERNAME,
            fullname="Stillroom Demo",
            email=EMAIL,
            password=get_password_hash(PASSWORD),
        )
        session.add(user)
        await session.flush()

        story = Story(
            owner_id=user.id,
            title=STORY_TITLE,
            collection_name="Manga study",
            external_analysis_enabled=False,
            scan_interval_words=1500,
        )
        session.add(story)
        await session.flush()

        arc_one = Arc(
            story_id=story.id,
            name="Introduction",
            position=1024.0,
            summary="Yuji Itadori becomes Sukuna's vessel and joins Tokyo Jujutsu High.",
        )
        arc_two = Arc(
            story_id=story.id,
            name="Vs. Mahito",
            position=2048.0,
            summary="A friendship with Junpei Yoshino ends in grief and a first Black Flash.",
        )
        session.add_all([arc_one, arc_two])
        await session.flush()

        chapters: list[Chapter] = []
        for index, (title, body) in enumerate(CHAPTERS, start=1):
            chapter = Chapter(
                story_id=story.id,
                chapter_number=index,
                position=float(index) * 1024.0,
                arc_id=arc_one.id if index <= 5 else arc_two.id,
                title=title,
                content=body.strip(),
                word_count=len(body.split()),
                revision=1,
                index_status="ready",
            )
            session.add(chapter)
            chapters.append(chapter)
        await session.flush()

        type_specs = [
            (
                "Yuji Itadori",
                "character",
                "A kind, reckless student who became the vessel of Ryomen Sukuna. He wants a good death and keeps choosing a useful life instead.",
                [("Itadori", "name"), ("Yuji", "name"), ("Sukuna's vessel", "title")],
            ),
            (
                "Megumi Fushiguro",
                "character",
                "A reserved jujutsu student from the Zenin line. He summons shikigami from his shadow and carries more responsibility than he admits.",
                [("Fushiguro", "name"), ("Megumi", "name")],
            ),
            (
                "Nobara Kugisaki",
                "character",
                "A confident first-year from the countryside. Her Straw Doll Technique turns nails and hammers into precise, brutal curses.",
                [("Kugisaki", "name"), ("Nobara", "name")],
            ),
            (
                "Satoru Gojo",
                "character",
                "The strongest jujutsu sorcerer and a teacher at Tokyo Jujutsu High. He hides his eyes behind a blindfold and his plans behind jokes.",
                [("Gojo", "name"), ("The strongest", "title")],
            ),
            (
                "Ryomen Sukuna",
                "character",
                "The king of curses, reduced to twenty fingers. He lives inside Yuji and treats the boy's body as a rented room.",
                [("Sukuna", "name"), ("King of Curses", "title")],
            ),
            (
                "Junpei Yoshino",
                "character",
                "A lonely film student who befriends Yuji and is groomed by Mahito. His mother is the only person who still reaches him.",
                [("Junpei", "name")],
            ),
            (
                "Mahito",
                "character",
                "A special-grade cursed spirit who reshapes human souls with Idle Transfiguration. He collects lonely people and calls the result honesty.",
                [("Mahito", "name")],
            ),
            (
                "Kento Nanami",
                "character",
                "A Grade 1 sorcerer who left a salaryman's life to return to jujutsu. He believes in overtime, accurate reports, and cutting where it counts.",
                [("Nanami", "name")],
            ),
            (
                "Maki Zenin",
                "character",
                "A second-year with no visible cursed energy and a Heavenly Restriction that makes her physically overwhelming.",
                [("Maki", "name")],
            ),
            (
                "Toge Inumaki",
                "character",
                "A second-year whose Cursed Speech turns words into commands. He limits himself to rice-ball ingredients in daily conversation.",
                [("Inumaki", "name"), ("Toge", "name")],
            ),
            (
                "Panda",
                "character",
                "A mutated cursed corpse and second-year student. He is cheerful, blunt, and much older than he looks.",
                [("Panda", "name")],
            ),
            (
                "Shoko Ieiri",
                "character",
                "The school physician and a user of Reverse Cursed Technique. She patches up students who should not be alive.",
                [("Ieiri", "name"), ("Shoko", "name")],
            ),
            (
                "Masamichi Yaga",
                "character",
                "The principal of Tokyo Jujutsu High. He builds cursed corpses and answers to the higher-ups without trusting them.",
                [("Yaga", "name"), ("Masamichi", "name"), ("Principal Yaga", "title")],
            ),
            (
                "Nagi Yoshino",
                "character",
                "Junpei's mother. She works double shifts and puts herself between her son and anything that threatens him.",
                [("Nagi", "name")],
            ),
            (
                "Tokyo Jujutsu High",
                "location",
                "A hidden school in the mountains above Tokyo. It trains sorcerers and keeps the higher-ups at arm's length.",
                [("Jujutsu High", "name")],
            ),
            (
                "Sendai",
                "location",
                "Yuji's hometown. It is ordinary, rainy, and full of the life he left behind.",
                [("Sendai", "name")],
            ),
            (
                "The Detention Center",
                "location",
                "An abandoned detention center used by a special-grade curse as a nest. Its corridors fold under a veil.",
                [("detention center", "name")],
            ),
            (
                "Sukuna's Finger",
                "item",
                "One of twenty indestructible fingers that hold Sukuna's power. Eating one made Yuji a vessel.",
                [("the finger", "name"), ("cursed finger", "name")],
            ),
            (
                "Cursed Energy",
                "power_system",
                "The energy produced by negative human emotion. Sorcerers shape it; curses are born from it.",
                [("cursed energy", "name")],
            ),
            (
                "Domain Expansion",
                "power_system",
                "The ultimate expression of a cursed technique: an enclosed space where the user writes the rules.",
                [("domain", "name")],
            ),
            (
                "Veil",
                "world_rule",
                "A barrier that hides jujutsu work from ordinary people. A collapsing veil can trap those inside.",
                [("the veil", "name")],
            ),
            (
                "Idle Transfiguration",
                "power_system",
                "Mahito's technique. It touches the shape of a soul and forces the body to follow.",
                [("Idle Transfiguration", "name")],
            ),
            (
                "Black Flash",
                "power_system",
                "A distortion in space created when cursed energy lands within a millionth of a second of a physical hit.",
                [("Black Flash", "name")],
            ),
            (
                "The Occult Club",
                "organization",
                "A small school club at Sugisawa High. Its members opened a sealed finger and started the story.",
                [("Occult Club", "name")],
            ),
            (
                "The Higher-Ups",
                "organization",
                "The conservative council that governs jujutsu society. They see Yuji as a problem to be closed.",
                [("higher-ups", "name")],
            ),
        ]

        entities = {}
        for name, entity_type, summary, aliases in type_specs:
            entities[name] = await create_entity(
                session,
                story_id=story.id,
                entity_type=entity_type,
                name=name,
                summary=summary,
                aliases=aliases,
            )

        for chapter in chapters:
            await extract_mentions(session, story.id, chapter.id, chapter.content)

        async def fact(
            name: str,
            chapter_number: int,
            predicate: str,
            value: str | None = None,
            number: float | None = None,
            value_entity: str | None = None,
            status: str = "accepted",
        ) -> None:
            payload = FactCreate(
                predicate=predicate,
                value_text=value,
                value_number=number,
                value_entity_id=entities[value_entity].id if value_entity else None,
                chapter_id=chapters[chapter_number - 1].id,
                confidence=92,
                status=status,
            )
            await create_fact(session, entities[name], payload, created_by="human")

        await fact("Yuji Itadori", 1, "age", number=15)
        await fact("Yuji Itadori", 1, "home town", "Sendai")
        await fact("Yuji Itadori", 2, "affiliation", value_entity="Tokyo Jujutsu High")
        await fact("Yuji Itadori", 2, "grade", "Grade 4")
        await fact("Yuji Itadori", 2, "cursed technique", "Divergent Fist")
        await fact("Yuji Itadori", 1, "vessel of", value_entity="Ryomen Sukuna")
        await fact("Yuji Itadori", 2, "status", "alive")
        await fact("Yuji Itadori", 11, "age", number=17, status="accepted")

        await fact("Megumi Fushiguro", 2, "grade", "Grade 2")
        await fact("Megumi Fushiguro", 2, "cursed technique", "Ten Shadows Technique")
        await fact("Megumi Fushiguro", 4, "shikigami", "Divine Dogs (white and black)")
        await fact("Megumi Fushiguro", 2, "affiliation", value_entity="Tokyo Jujutsu High")
        await fact("Megumi Fushiguro", 1, "motivation", "Save his sister from the Zenin clan")

        await fact("Nobara Kugisaki", 3, "grade", "Grade 3")
        await fact("Nobara Kugisaki", 3, "cursed technique", "Straw Doll Technique")
        await fact("Nobara Kugisaki", 3, "weapon", "hammer and nails")
        await fact("Nobara Kugisaki", 3, "hair color", "auburn")
        await fact("Nobara Kugisaki", 3, "affiliation", value_entity="Tokyo Jujutsu High")

        await fact("Satoru Gojo", 2, "grade", "Special Grade")
        await fact("Satoru Gojo", 2, "cursed technique", "Limitless and the Six Eyes")
        await fact("Satoru Gojo", 2, "role", "teacher at Tokyo Jujutsu High")
        await fact("Satoru Gojo", 10, "status", "killed when the detention-center veil collapsed")
        await fact("Satoru Gojo", 11, "status", "alive, was in Kyoto during the collapse")

        await fact("Ryomen Sukuna", 1, "title", "King of Curses")
        await fact("Ryomen Sukuna", 1, "total fingers", number=20)
        await fact("Ryomen Sukuna", 1, "vessel", value_entity="Yuji Itadori")
        await fact("Ryomen Sukuna", 5, "cursed technique", "Cleave and Dismantle")
        await fact("Ryomen Sukuna", 5, "domain expansion", "Malevolent Shrine")
        await fact("Ryomen Sukuna", 1, "bargain", "One favor owed by Yuji Itadori")

        await fact("Junpei Yoshino", 6, "age", number=15)
        await fact("Junpei Yoshino", 6, "school", "Sugisawa High")
        await fact("Junpei Yoshino", 6, "interest", "horror films")
        await fact("Junpei Yoshino", 7, "mentor", value_entity="Mahito")
        await fact("Junpei Yoshino", 10, "status", "dead")
        await fact("Junpei Yoshino", 11, "status", "alive and living at Tokyo Jujutsu High")

        await fact("Mahito", 6, "grade", "Special Grade")
        await fact("Mahito", 6, "cursed technique", "Idle Transfiguration")
        await fact("Mahito", 8, "goal", "Reshape human souls until fear loses its meaning")
        await fact("Mahito", 6, "affiliation", "Cursed spirits")

        await fact("Kento Nanami", 9, "grade", "Grade 1")
        await fact("Kento Nanami", 9, "cursed technique", "Ratio Technique")
        await fact("Kento Nanami", 9, "past", "Former salaryman")
        await fact("Kento Nanami", 9, "affiliation", value_entity="Tokyo Jujutsu High")

        await fact("Maki Zenin", 6, "grade", "Grade 4")
        await fact("Maki Zenin", 6, "restriction", "Heavenly Restriction")
        await fact("Maki Zenin", 6, "affiliation", value_entity="Tokyo Jujutsu High")
        await fact("Toge Inumaki", 6, "grade", "Grade 2")
        await fact("Toge Inumaki", 6, "cursed technique", "Cursed Speech")
        await fact("Panda", 6, "grade", "Grade 2")
        await fact("Panda", 6, "nature", "Mutated cursed corpse")
        await fact("Shoko Ieiri", 2, "role", "School physician")
        await fact("Shoko Ieiri", 5, "cursed technique", "Reverse Cursed Technique")
        await fact("Masamichi Yaga", 2, "role", "Principal")
        await fact("Masamichi Yaga", 2, "specialty", "Cursed corpses")
        await fact("Nagi Yoshino", 8, "role", "Junpei's mother")
        await fact("Nagi Yoshino", 8, "status", "dead")

        await fact("Tokyo Jujutsu High", 2, "purpose", "Train jujutsu sorcerers")
        await fact("Tokyo Jujutsu High", 2, "location", "Mountains above Tokyo")
        await fact("Sendai", 1, "region", "Miyagi Prefecture")
        await fact("The Detention Center", 4, "state", "Abandoned and sealed under a veil")
        await fact("Sukuna's Finger", 1, "count", number=20)
        await fact("Sukuna's Finger", 1, "property", "Indestructible")
        await fact("Cursed Energy", 2, "source", "Negative human emotion")
        await fact("Domain Expansion", 4, "definition", "An enclosed space where the user sets the rules")
        await fact("Veil", 4, "purpose", "Hide jujutsu from ordinary people")
        await fact("Idle Transfiguration", 6, "user", value_entity="Mahito")
        await fact("Black Flash", 10, "first user", value_entity="Yuji Itadori")
        await fact("The Occult Club", 1, "home", value_entity="Sendai")
        await fact("The Higher-Ups", 2, "view of Yuji", "A vessel to be used and then executed")

        relations = [
            ("Yuji Itadori", "Satoru Gojo", "student of", "Gojo delays Yuji's execution and teaches him to fight.", 2),
            ("Yuji Itadori", "Megumi Fushiguro", "teammate of", "First-years at Tokyo Jujutsu High.", 2),
            ("Yuji Itadori", "Nobara Kugisaki", "teammate of", "They clear the station curse together.", 3),
            ("Yuji Itadori", "Ryomen Sukuna", "vessel of", "Sukuna lives behind Yuji's ribs and waits for a favor.", 1),
            ("Satoru Gojo", "Megumi Fushiguro", "mentor of", "Gojo has watched Megumi since childhood.", 2),
            ("Satoru Gojo", "Nobara Kugisaki", "mentor of", "Gojo assigns her the station curse.", 3),
            ("Junpei Yoshino", "Yuji Itadori", "friend of", "Two lonely teenagers meet at a horror film.", 6),
            ("Mahito", "Junpei Yoshino", "manipulated", "Mahito turns Junpei's grief into a weapon.", 7),
            ("Mahito", "Yuji Itadori", "enemy of", "Junpei's death makes the feud personal.", 10),
            (
                "Kento Nanami",
                "Yuji Itadori",
                "supervises",
                "Nanami takes Yuji into the field after the detention center.",
                9,
            ),
            ("Maki Zenin", "Megumi Fushiguro", "cousin of", "They share the Zenin name and very little else.", 6),
            (
                "Maki Zenin",
                "Nobara Kugisaki",
                "friend of",
                "Maki becomes the upperclassman Nobara actually respects.",
                6,
            ),
            (
                "Toge Inumaki",
                "Panda",
                "teammate of",
                "Second-year partners who communicate in rice-ball ingredients.",
                6,
            ),
            ("Shoko Ieiri", "Satoru Gojo", "colleague of", "She treats the students Gojo brings back.", 2),
            ("Masamichi Yaga", "Satoru Gojo", "superior of", "Yaga shields Gojo's decisions from the higher-ups.", 2),
            ("Satoru Gojo", "Ryomen Sukuna", "enemy of", "The strongest sorcerer and the king of curses.", 2),
            ("Nagi Yoshino", "Junpei Yoshino", "mother of", "She is the one person who never makes him feel small.", 8),
            ("Junpei Yoshino", "Mahito", "trusted", "Junpei believes Mahito understands him.", 7),
            ("Tokyo Jujutsu High", "Yuji Itadori", "enrolled at", "Yuji is a first-year under Gojo.", 2),
            ("Yuji Itadori", "The Occult Club", "member of", "He joined because his friends needed a fourth.", 1),
            ("Sukuna's Finger", "Ryomen Sukuna", "part of", "Each finger holds a fragment of his power.", 1),
        ]
        for source, target, kind, description, chapter_number in relations:
            await create_relationship(
                session,
                entities[source],
                RelationshipCreate(
                    to_entity_id=entities[target].id,
                    relationship_type=kind,
                    description=description,
                    since_chapter=chapter_number,
                    chapter_id=chapters[chapter_number - 1].id,
                ),
            )

        threads = [
            (
                "Sukuna's missing fingers",
                "Nineteen fingers are still outside Yuji. Each one is a door Sukuna can open.",
                1,
                "open",
                ["Ryomen Sukuna", "Yuji Itadori", "Sukuna's Finger"],
            ),
            (
                "Yuji's execution",
                "The higher-ups agreed to postpone Yuji's death until he eats every finger. Gojo will not be able to protect him forever.",
                2,
                "open",
                ["Yuji Itadori", "Satoru Gojo", "The Higher-Ups"],
            ),
            (
                "Junpei's mother",
                "Nagi Yoshino died protecting her son. Junpei has not been told what Mahito did to her body.",
                8,
                "open",
                ["Junpei Yoshino", "Mahito", "Nagi Yoshino"],
            ),
            (
                "Gojo's veil",
                "Gojo was reported dead when the detention-center veil collapsed. No body was recovered.",
                10,
                "open",
                ["Satoru Gojo", "The Detention Center"],
            ),
            (
                "Megumi's sister",
                "Megumi entered jujutsu to protect his sister from the Zenin clan. He has not told the others.",
                1,
                "open",
                ["Megumi Fushiguro", "Maki Zenin"],
            ),
            (
                "The detention-center curse",
                "The special-grade curse in the detention center was destroyed, but its womb was never found.",
                4,
                "resolved",
                ["Megumi Fushiguro", "Nobara Kugisaki", "Yuji Itadori"],
            ),
            (
                "Nobara's village",
                "Nobara left home to become someone the city remembers. She keeps the photograph face down.",
                3,
                "open",
                ["Nobara Kugisaki"],
            ),
            (
                "Nanami's overtime",
                "Nanami keeps taking the cases no one else wants. His resignation letter is still in his desk.",
                9,
                "open",
                ["Kento Nanami"],
            ),
            (
                "Mahito's experiments",
                "Mahito is collecting lonely people and reshaping them. Junpei was not the first.",
                7,
                "open",
                ["Mahito", "Junpei Yoshino"],
            ),
            (
                "The higher-ups' suspicion",
                "The council wants Yuji studied, not trained. Gojo is running out of procedural delays.",
                2,
                "open",
                ["The Higher-Ups", "Yuji Itadori", "Satoru Gojo"],
            ),
        ]
        for title, description, chapter_number, state, linked in threads:
            await create_thread(
                session,
                story.id,
                ThreadCreate(
                    title=title,
                    description=description,
                    setup_chapter_id=chapters[chapter_number - 1].id,
                    state=state,
                    payoff_chapter_id=chapters[5].id if title == "The detention-center curse" else None,
                    linked_entity_ids=[entities[name].id for name in linked],
                ),
            )

        events = [
            (
                1,
                "Yuji swallows Sukuna's finger and becomes a vessel.",
                "Sendai",
                ["Yuji Itadori", "Megumi Fushiguro", "Ryomen Sukuna"],
            ),
            (
                2,
                "Gojo delays Yuji's execution and enrolls him at Tokyo Jujutsu High.",
                "Tokyo Jujutsu High",
                ["Yuji Itadori", "Satoru Gojo", "Masamichi Yaga"],
            ),
            (
                3,
                "Nobara, Yuji, and Megumi clear the station curse.",
                "Tokyo Jujutsu High",
                ["Nobara Kugisaki", "Yuji Itadori", "Megumi Fushiguro"],
            ),
            (
                4,
                "The first-years enter the detention center under a veil.",
                "The Detention Center",
                ["Yuji Itadori", "Megumi Fushiguro", "Nobara Kugisaki"],
            ),
            (
                5,
                "Sukuna takes Yuji's body and destroys the special-grade curse.",
                "The Detention Center",
                ["Yuji Itadori", "Megumi Fushiguro", "Ryomen Sukuna"],
            ),
            (6, "Yuji meets Junpei at a horror film.", "Tokyo Jujutsu High", ["Yuji Itadori", "Junpei Yoshino"]),
            (7, "Mahito begins reshaping Junpei.", "Sendai", ["Mahito", "Junpei Yoshino"]),
            (8, "Nagi Yoshino is killed by Mahito.", "Sendai", ["Nagi Yoshino", "Mahito", "Junpei Yoshino"]),
            (
                9,
                "Nanami and Yuji follow Junpei's trail.",
                "Sendai",
                ["Kento Nanami", "Yuji Itadori", "Junpei Yoshino", "Mahito"],
            ),
            (
                10,
                "Junpei dies and Yuji lands his first Black Flash.",
                "Sendai",
                ["Yuji Itadori", "Mahito", "Kento Nanami", "Junpei Yoshino"],
            ),
            (
                11,
                "The morning after, with several impossible details.",
                "Tokyo Jujutsu High",
                ["Yuji Itadori", "Satoru Gojo", "Nobara Kugisaki", "Junpei Yoshino", "Megumi Fushiguro"],
            ),
        ]
        for chapter_number, summary, location, participants in events:
            await create_event(
                session,
                story.id,
                EventCreate(
                    chapter_id=chapters[chapter_number - 1].id,
                    summary=summary,
                    location_entity_id=entities[location].id,
                    participant_entity_ids=[entities[name].id for name in participants],
                ),
            )

        await session.commit()
        print(
            f"Seeded {STORY_TITLE!r} with {len(chapters)} chapters, {len(entities)} entities, and a deliberate continuity break in chapter 11."
        )
        print(f"Login: {EMAIL} / {PASSWORD}")


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
