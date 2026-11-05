#!/usr/bin/env python3
"""Apply the author's contextual rewrite to the active Equal Shares plan."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path


KENT = (
    "Kent Brentwood: exact established main-character likeness, short dark receding hair, "
    "distinctive dark mustache, teal cardigan, cream shirt, charcoal trousers, worn brown shoes"
)
NARRATOR = (
    "The Narrator: a distinct man in his late fifties, lean face, neatly combed dark-gray hair, "
    "dark 1960s suit, white shirt and narrow black tie; he must never resemble Kent"
)
RYANN = "Ryann Sally: exact established estate administrator and council moderator, black hair in a low bun, rectangular glasses, burgundy suit, white blouse"
AVERY = "Avery Renfield: exact established financially secure older brother, clean-cut salt-and-pepper hair, navy coat or jacket, pale blue shirt"
FAITH = "Faith White: exact established pastor, dignified older man with neatly trimmed gray beard, warm beige clerical clothing"
DORIS = "Doris Lovelay: exact established elderly mother, short softly curled gray hair, warm expressive face, cream knit cardigan"
VOLUNTEER = "Mutual-aid volunteer: exact established older woman with short gray hair, beige cardigan, calm kind expression"
HOUSING_REP = "Housing representative: exact auburn-haired woman in her early forties from the corridor reference, plain navy raincoat and practical office clothing"


def h3_frames(seconds: int) -> int:
    base = max(5, round(seconds * 24))
    return base + (5 - base % 17) % 17


def d(start: float, end: float, speaker: str, line: str, delivery: str = "") -> dict:
    label = f"{speaker}{', ' + delivery if delivery else ''}: “{line}”"
    return {"start": start, "end": end, "speaker": speaker, "delivery": delivery, "line": line, "label": label}


def ref(scene: int, number: int) -> str:
    return f"frames/scene_{scene:03d}/boundary_{number:02d}.png"


def new_ref(folder: str, number: int) -> str:
    return f"frames/{folder}/boundary_{number:02d}.png"


def opening_ref(name: str) -> str:
    return f"frames/scene_000/{name}"


PROLOGUE = [
    {
        "id": "00A", "scene": "Prologue — The Super Nice Zone", "duration": 15,
        "action": "Black-and-white vintage television prologue. The Narrator stands foreground under a controlled spotlight. Behind him is a sterile sitcom-set waiting room with blank walls, exactly one chair at screen-left, a female receptionist alone behind a staff-only check-in window, and a separate open entrance doorway at far screen-right. No visitors are present yet. He addresses the camera without moving far.",
        "dialogue": [d(1, 14, "Narrator", "In a world of total equality, fairness, kindness, and other generous human traits get out of control.", "measured Twilight-Zone-like cadence")],
        "first_frame": opening_ref("boundary_00_v2.png"), "audio": "Dry studio room tone and a restrained original eerie orchestral underscore.",
    },
    {
        "id": "00B", "scene": "Prologue — The Super Nice Zone", "duration": 15,
        "action": "Remain on the Narrator in the same black-and-white waiting-room set. The woman receptionist stays alone behind the staff window, the open entrance remains separate at screen-right, and the public room remains empty. Use a nearly imperceptible push-in while he poses the paradox directly to the viewer.",
        "dialogue": [d(1, 14, "Narrator", "If all people feel that someone without should be helped so they are no longer without, but in the process they become without, how do people really help each other?", "measured and ominously curious")],
        "first_frame": opening_ref("boundary_00_v2.png"), "audio": "Same original subdued speculative underscore.",
    },
    {
        "id": "00C", "scene": "Prologue — The Super Nice Zone", "duration": 13,
        "action": "The Narrator finishes the opening question. The camera moves past him into the still-empty public waiting room and gradually crops him from view. End on the woman receptionist alone behind the check-in window, the separate entrance doorway open at screen-right, and the single chair at screen-left.",
        "dialogue": [d(1, 12, "Narrator", "When no one else feels that they are more important than the next person, how do people decide who gets what?", "thoughtful")],
        "first_frame": opening_ref("boundary_00_v2.png"), "last_frame": opening_ref("boundary_entry_start_v2.png"), "audio": "Original low suspense cue; no recognizable television theme.",
    },
    {
        "id": "00D", "scene": "Prologue — The Chair", "duration": 12,
        "action": "Black-and-white sitcom-set wide shot with no Narrator visible. Begin with the public waiting room empty. Male Visitor One walks through the open entrance doorway into the public room; exactly one second later, distinct Male Visitor Two walks through the same doorway behind him. They form a short line at the receptionist window, check in one after the other with the woman receptionist, then both walk toward the room's only chair. Neither man ever enters the staff area or appears behind the reception counter.",
        "dialogue": [d(1, 5, "Narrator, off-screen", "If there’s one chair in a room and two people.")],
        "first_frame": opening_ref("boundary_entry_start_v2.png"), "last_frame": opening_ref("boundary_01_v2.png"), "audio": "Soft footsteps through the doorway, two quick check-ins, restrained original underscore.",
    },
    {
        "id": "00D2", "scene": "Prologue — The Chair", "duration": 10,
        "action": "Continue with both male visitors on the public side beside the single chair while the woman receptionist observes from behind the window. The two men repeatedly and politely offer the chair to each other. They reach a reluctant agreement, and Male Visitor One sits while Male Visitor Two remains standing. The receptionist never leaves the staff window and neither man moves behind the counter.",
        "dialogue": [d(1, 9, "Narrator, off-screen", "Both people insist that the other person takes the seat. Even if one does take it, the other goes without.")],
        "first_frame": opening_ref("boundary_01_v2.png"), "last_frame": opening_ref("boundary_02_v2.png"), "audio": "Restrained original underscore, cloth movement, and one soft chair creak.",
    },
    {
        "id": "00E", "scene": "Prologue — The Chair", "duration": 12,
        "action": "Shot-reverse-shot feeling within one controlled move: begin focused on Person One sitting and looking upward, then shift focus to Person Two standing and looking downward. Both become visibly anxious without speaking.",
        "dialogue": [d(1, 11, "Narrator, off-screen", "The sitting now looks up at the standing, and the standing looks down at the sitting. Both people are now filled with debilitating anxiety.")],
        "first_frame": opening_ref("boundary_02_v2.png"), "last_frame": opening_ref("boundary_03_v2.png"), "audio": "Sterile room tone, faint clock tick, restrained tension cue.",
    },
    {
        "id": "00F", "scene": "Prologue — The Chair", "duration": 15,
        "action": "Black-and-white close composition centered on Person One sitting. Person Two is only partly visible at frame edge. Person One wants to surrender the chair but stays frozen, worried that returning the gift would itself be rude.",
        "dialogue": [d(1, 14, "Narrator, off-screen", "One wants to give their chair away so the other can be comfortable and sit. They won’t say anything, though, because they dare not be rude by gifting a gift back to the giver.")],
        "first_frame": opening_ref("boundary_02_v2.png"), "audio": "Clock tick grows slightly louder under the original score.",
    },
    {
        "id": "00G", "scene": "Prologue — The Chair", "duration": 15,
        "action": "Black-and-white close composition centered on Person Two standing. Person One is only partly visible. Sweat forms at the standing person's temple; their posture reveals painful, tired feet.",
        "dialogue": [d(1, 14, "Narrator, off-screen", "The standing looks down at the sitting, sweating in discomfort. They had been on their feet all day and had been looking forward to finally getting to sit.")],
        "first_frame": opening_ref("boundary_03_v2.png"), "audio": "Sterile room tone and a faint shoe-leather creak.",
    },
    {
        "id": "00H", "scene": "Prologue — The Chair", "duration": 15,
        "action": "Stay on the standing person, who subtly shifts weight from one sore foot to the other yet refuses to ask for the chair. The seated person remains frozen at the edge of frame.",
        "dialogue": [d(1, 14, "Narrator, off-screen", "Of course they would never ask for the seat that they gave to another out of kindness. But the consequence of inaction means more suffering and waiting—waiting to take the weight off their calloused and blistered feet.")],
        "first_frame": opening_ref("boundary_03_v2.png"), "audio": "Quiet clock tick, subtle original tension cue, no melodramatic sting.",
    },
    {
        "id": "00I", "scene": "Prologue — The Chair", "duration": 12,
        "action": "Both waiting people freeze completely in the background. The practical set lights fade as the camera pulls back to reveal the Narrator foreground under a lone spotlight. The waiting-room background begins dissolving away after his final question.",
        "dialogue": [d(2, 11, "Narrator", "Both people are frozen by their own anxieties, wanting to make the world a better place—but at what cost?", "direct to camera")],
        "first_frame": opening_ref("boundary_04_v2.png"), "audio": "Original ominous orchestral rise, then a breath of silence.",
    },
    {
        "id": "00J", "scene": "Prologue — Kent", "duration": 12,
        "action": "Return to full color. Aerial view lowers toward Kent walking on a bright city sidewalk until his face and teal cardigan are clear. The Narrator remains off-screen.",
        "dialogue": [d(1, 11, "Narrator, off-screen", "This is the world that we are in, and a man walking through it, trying to get by. His name—Kent Brentwood.")],
        "first_frame": ref(1, 0), "audio": "City ambience with the speculative underscore changing from monochrome austerity to warmer instrumentation.",
    },
    {
        "id": "00K", "scene": "Prologue — Kent", "duration": 15,
        "action": "Kent freezes mid-step in color. The surrounding street darkens slightly. The Narrator walks into the frozen frame and stands under a spotlight, with Kent behind him.",
        "dialogue": [d(1, 14, "Narrator", "Kent is at an inflection point that some call midlife. He’s done everything he can in life to be a good person.")],
        "first_frame": new_ref("scene_000", 5), "audio": "Frozen city ambience under an original low orchestral cue.",
    },
    {
        "id": "00L", "scene": "Prologue — Kent", "duration": 15,
        "action": "The Narrator remains foreground while Kent and the city stay frozen and dimmed behind him. Maintain the same composition and spotlight.",
        "dialogue": [d(1, 14, "Narrator", "He’s taken care of his mom. He’s been a loving brother and uncle. He’s always worked hard, and has always paid his debts. He has never hesitated to help someone he has seen in need.")],
        "first_frame": new_ref("scene_000", 5), "audio": "Same original restrained orchestral cue.",
    },
    {
        "id": "00M", "scene": "Prologue — Kent", "duration": 15,
        "action": "Same frozen Kent tableau. The Narrator's expression grows more sober, foreshadowing the story without becoming theatrical.",
        "dialogue": [d(1, 14, "Narrator", "But always doing the right thing does not mean the right things happen. Kent has gone in and out of debt his entire life. He’s about to be evicted. His mother is sick.")],
        "first_frame": new_ref("scene_000", 5), "audio": "Original subdued tension cue.",
    },
    {
        "id": "00N", "scene": "Prologue — Kent", "duration": 15,
        "action": "Same composition. The Narrator prepares to name the story's strange zone; Kent remains frozen behind him.",
        "dialogue": [d(1, 14, "Narrator", "Kent is about to be challenged, and he’s about to challenge everyone around him. The veil of absolute kindness and equality is about to be lifted off his head.")],
        "first_frame": new_ref("scene_000", 5), "audio": "Original suspense cue builds gently.",
    },
    {
        "id": "00O", "scene": "Prologue — Kent", "duration": 12,
        "action": "The Narrator delivers the title, then his spotlight fades. He steps aside, the city returns to normal exposure, and frozen Kent resumes walking naturally.",
        "dialogue": [d(1, 7, "Narrator", "Kent has just walked into—the Super Nice Zone.", "deliberate title cadence")],
        "first_frame": new_ref("scene_000", 5), "last_frame": ref(1, 0), "audio": "A short original anthology-style sting, then ordinary city ambience. Do not imitate any existing television theme.",
    },
]


ACTION = {
    "01B": "At the automated entrance, a wealthy commuter warmly greets an unhoused man. The gate denies the unhoused man entry. They face one another, never the camera, and remain sincere.",
    "01C": "Kent observes as the wealthy commuter gives the unhoused man a visible wad of cash despite the gate denial. Nobody challenges the gate. Kent absorbs the contradiction and continues walking.",
    "02B": "Doris worries that the retirement home is too expensive. Kent reassures her while protecting her from his financial fear. She reveals that she has seen the bill and praises him as a son.",
    "03A": "Avery arrives with flowers, embraces Doris and Kent, apologizes for being late, and explains that his company is closing a merger. Doris warmly tells him he is fine and acknowledges that he is busy.",
    "04C": "The congregation puts generous amounts of money into a full donation plate. When it reaches Kent, he glances at his full wallet but gives nothing, following the teaching about protecting his household. Keep his choice restrained, not greedy.",
    "05B": "Doris wakes near the end of her life and tells Kent he has always been a good son and that she wishes she could have given him more. She thanks him before dying peacefully as he holds her hand.",
    "06C": "Alone, Kent retrieves the retirement-home invoice. Insert a readable close view of the bill headed OAK GROVE RETIREMENT HOME with the total $6,76,767 exactly as written. Kent drops the papers onto the table, presses a hand to his temple, and bends forward in stress.",
    "07C": "Kent silently realizes his share cannot cover the care debt. Ryann notices discomfort and rapidly offers a quirky choice between a G2 pen and a gel pen instead of naming the financial problem.",
    "08B": "Kent says he would never question his mother's loving choice, stressing the words loving choice with a faintly resentful edge while remaining socially composed.",
    "08C": "Ryann warmly insists Kent is a good man who deserves whatever he wants. Kent grips his cup in frustrated disbelief at the contradiction.",
    "09B": "Avery offers Kent part of his inheritance and says he already has all the money he needs. Kent refuses because accepting would feel wrong.",
    "09C": "Kent mentions Mara's school fund. Avery says it is already covered and that helping would bring him and Mara pleasure. Kent appreciatively but firmly refuses the money.",
    "10B": "Faith addresses each brother directly, looking at Kent for the first sentence and Avery for the second. Her sincere guidance reframes Kent's refusal and Avery's acceptance of that limit as loving acts.",
    "11B": "At the mutual-aid center, Kent places the received gift at the pleasant automated terminal. The machine welcomes him, records the gift, and proposes return paths.",
    "11C": "A volunteer tells Kent to ignore the machine and insists he owes nothing. Kent responds literally that a mutual-aid group requires him to aid mutually.",
    "12C": "After exhausted volunteer work, the terminal announces only a nineteen-percent reduction. Kent initially reacts, then forces a tired optimistic smile and tries to see the brighter side.",
    "13B": "Kent remembers Doris's story about the bird bracelet. Present a clearly readable cinematic thought bubble above and beside Kent containing a warm flashback of Doris speaking with him; retain a photorealistic live-action frame rather than a comic-book style.",
    "15B": "Ryann announces identical modest grants to applicants with unequal needs. Another applicant is visibly relieved while Kent realizes the same amount cannot stop his eviction.",
    "16B": "Full podium visible with open space beside Kent for Ryann to enter in the later handoff shot. Kent thanks Ryann and begins explaining that people do not all have the same needs. He scans the hopeful audience and continues instead of retreating.",
    "17C": "Kent folds away the paper marked UNFAIR, sits back, exhales, and looks toward the ceiling with mild frustration.",
    "20B": "A congregation member blurts that the collected aid is not enough, then nervously changes the meaning to not enough to express care.",
    "21C": "Strict side-profile tracking composition: the sidewalk runs horizontally left to right and Kent walks sadly across frame after seeing the missed-housing-appointment reminder.",
    "24A": "Council-room wide establishing shot. Identical sand timers sit before speakers. Ryann stands at the full podium and opens the session while Kent waits nearby.",
    "28C": "The courteous crew locks Kent's former apartment. The crew lead apologizes sincerely; Kent answers with a small, dry, sarcastic okay. The lock remains closed.",
    "29B": "Avery gives Kent an umbrella and emergency cash. Kent accepts, discreetly returns Doris's will copy in the envelope, smiles, and affectionately calls his brother Ave.",
    "30C": "Rear view of Kent walking away from the camera into a warm sunset along the city sidewalk, carrying one box. He recedes toward the horizon. Fade to black for the closing thought.",
}


DIALOGUE = {
    "01B": [d(0.5, 7, "Wealthy commuter", "Good day! I can’t let you in, but I can give you a sincere compliment.", "sincere"), d(7.2, 12.5, "Unhoused man", "Oh, that sure is kind of you. I really need money, though.", "warm but practical")],
    "02B": [d(0.5, 6, "Doris", "Kent, I am thankful, but I hope this place isn’t too expensive.", "apologetic"), d(6, 9.5, "Kent", "Don’t you worry, Mom. You deserve the best.", "steady"), d(9.5, 15, "Doris", "I saw the bill for this place. How did I get such a good son?", "faint smile")],
    "03A": [d(0.5, 9, "Avery", "Hey, Mom! Hey, Kent! I’m sorry I’m late. We’re closing a merger right now with our company.", "arriving warmly"), d(10, 14, "Doris", "You’re fine, son. I know you’re busy.", "reassuring")],
    "05B": [d(1, 6, "Doris", "You have always been a good son. I wish I could have given you more.", "faint but warm"), d(7, 9, "Doris", "Thank you, Kent.", "soft")],
    "07C": [d(4, 8, "Ryann Sally", "Would you like a G2 pen, or perhaps a gel pen instead?", "fast and quirky")],
    "08B": [d(2, 6, "Kent", "I would never question Mom’s loving choice.", "composed with faint resentment on loving choice")],
    "08C": [d(1, 7, "Ryann Sally", "Kent, of course you wouldn’t. You are such a good man. You deserve whatever you want.", "warm")],
    "09B": [d(1, 3, "Avery", "Take part of mine.", "earnest"), d(3.5, 5, "Kent", "I can’t.", "immediate"), d(5.5, 10, "Avery", "I mean it. I have all the money I need already.", "sincere")],
    "09C": [d(0.5, 2, "Kent", "Mara’s school fund.", "calm"), d(2.2, 10, "Avery", "That’s already taken care of. It would bring great pleasure to me and Mara if you would take it.", "reassuring"), d(10, 15, "Kent", "Brother, I appreciate the offer, but I just wouldn’t feel right taking money from you.", "gentle")],
    "10B": [d(1, 8, "Faith White", "Kent, you should not wound the brother who tries to ease financial suffering by refusing the help.", "calm, looking at Kent"), d(8, 14, "Faith White", "But Avery, accepting someone’s limits can also be a loving act.", "turning to Avery")],
    "11B": [d(1, 13, "Terminal voice", "Welcome to your local mutual-aid center. Gift recorded. Suggested return paths: three volunteer hours, one mentoring session, or a future kindness of comparable warmth.", "pleasant")],
    "11C": [d(1, 5, "Volunteer", "Pay no mind to the machine. You owe nothing.", "kind"), d(5.5, 11.5, "Kent", "What do you mean? This is a mutual-aid group. I need to aid mutually.", "sincere and literal")],
    "12C": [d(0.5, 4.5, "Terminal voice", "Return value logged. Grocery box balance reduced by nineteen percent.", "cheerful"), d(4.7, 5.7, "Kent", "Nineteen?", "exhausted"), d(6, 10.5, "Kent", "Well, at least it’s nineteen percent less and not more.", "forcing optimism")],
    "13B": [d(1, 14, "Doris, remembered voice", "Your father and I had given all our money away to help our neighbor. We were broke, but he bought the bracelet anyway, which made it very romantic, but also financially irresponsible.", "affectionate")],
    "15B": [d(2, 7, "Ryann Sally", "Each approved applicant will receive the same modest housing grant, in equal recognition of equal dignity.", "warm")],
    "16B": [d(1, 5, "Kent", "Thank you, Ryann. I would like to add that some of us—", "cautious"), d(6, 10, "Kent", "don’t have the same exact needs as everyone else.", "continuing after looking around")],
    "20B": [d(2, 4, "Congregation member", "This isn’t enough.", "blurting"), d(5, 8, "Congregation member", "I mean—not enough to express my care.", "nervously correcting")],
    "22B": [d(1, 8, "Doris recording", "Equal shares. Equal love. No one should be hurt by wondering who mattered more. If either of you needs more, I trust you will be kind to each other.", "warm")],
    "22C": [d(3, 6, "Kent", "We are, Mom. That’s the problem.", "quiet")],
    "28C": [d(3, 5, "Crew lead", "I am sorry.", "sincere"), d(5, 6, "Kent", "Okay.", "dry and sarcastic")],
    "29B": [d(3, 6, "Kent", "Thanks, Ave.", "smiling affectionately")],
    "30B": [d(2, 5, "Aid worker", "Your application has been compassionately denied.", "gentle")],
}


DURATION = {
    "01B": 13, "02B": 15, "03A": 15, "05B": 10, "07C": 9, "08C": 8,
    "09B": 11, "09C": 15, "10B": 15, "11B": 14, "11C": 12, "12C": 11,
    "13B": 15, "16B": 11, "20B": 9,
}


INSERT_AFTER = {
    "14C": [
        {
            "id": "14D", "scene": "The Drive", "duration": 15,
            "action": "Kent drives alone through the city, visibly stressed, hands steady on the wheel and eyes on the road. He thinks about rent and the bracelet while the car passes through ordinary daylight traffic.",
            "dialogue": [d(1, 15, "Kent, internal voice", "I have no idea how I’m ever going to pay rent. The bracelet was the last thing I have that’s worth something. I should have put off paying the mutual-aid group and sold it instead.", "frustrated")],
            "first_frame": new_ref("scene_014_drive", 0), "audio": "Car interior road noise under Kent's clear internal monologue.",
        },
        {
            "id": "14E", "scene": "The Drive", "duration": 13,
            "action": "Continue the same driving shot with a modest angle change. Kent remembers Faith White's teaching and recognizes that giving away the bracelet harmed him personally.",
            "dialogue": [d(1, 12, "Kent, internal voice", "That’s what Pastor White said: give to others in need, but not if it hurts you personally by giving it away.", "realizing the contradiction")],
            "first_frame": new_ref("scene_014_drive", 0), "audio": "Continuous car ambience and restrained original dramatic underscore.",
        },
    ],
    "16C": [
        {
            "id": "16D", "scene": "Almost — Continued", "duration": 15,
            "action": "Kent remains at the full podium and elaborates. Show the whole podium and preserve open space on one side. He describes a lifetime spent protecting other people's comfort and his own lost standard of living.",
            "dialogue": [d(1, 14, "Kent", "I have spent my whole life trying to make sure that everyone has what they need to live up to the comfortable standard of living I’ve grown used to. At least, I had grown used to it.", "earnest")],
            "first_frame": new_ref("scene_016", 7), "audio": "Quiet council-room ambience and clear podium microphone.",
        },
        {
            "id": "16E", "scene": "Almost — Continued", "duration": 15,
            "action": "Continue Kent's speech from the same podium with a slightly closer angle. He explains that the cause is just but not every consequence is just. One audience member gives a quick uncertain chuckle; otherwise the room is silent.",
            "dialogue": [d(1, 14, "Kent", "I’ve sacrificed so much of my comfort to keep others comfortable, which is how we have decided to live our lives. I know that this is a just cause, but not all the consequences are just.", "controlled conviction")],
            "first_frame": new_ref("scene_016", 7), "audio": "Podium microphone, one brief uncertain audience chuckle near the end, then silence.",
        },
        {
            "id": "16F", "scene": "Almost — Continued", "duration": 10,
            "action": "Kent finishes by proposing that people can help one another without destroying their own livelihoods. Hold the confused silent audience reaction after he finishes.",
            "dialogue": [d(1, 7, "Kent", "We can absolutely do things differently so that we can help one another without sacrificing our own livelihood.", "hopeful")],
            "first_frame": new_ref("scene_016", 7), "audio": "Council-room silence after the final words.",
        },
        {
            "id": "16G", "scene": "Ryann Retakes the Podium", "duration": 15,
            "action": "Ryann hurries into the open space beside the full podium, nervously nudges Kent aside, and takes control of the microphone. Kent walks back toward his seat while the camera remains on Ryann. She awkwardly thanks him, regains composure, and opens the floor. Hard cut at the end.",
            "dialogue": [d(1, 6, "Ryann Sally", "Um, thank you, Kent, for—uh—that.", "nervous and confused, awkward emphasis on that"), d(7, 14, "Ryann Sally", "Now I would like to open the floor to anyone else who would like to make a comment on the housing grant.", "recovering composure")],
            "first_frame": new_ref("scene_016", 7), "audio": "Podium microphone and quiet room tone; hard audio cut at the end.",
        },
    ],
}


REPLACEMENT_SCENES = {
    14: [
        {
            "id": "14A", "scene": "Kind Refusal", "duration": 15,
            "action": "Kent offers Doris's wrapped bird bracelet to the older volunteer at the mutual-aid counter. She refuses because he owes nothing; he keeps insisting with visible desperation while she is confused by his belief that aid created debt.",
            "dialogue": [d(1, 5, "Volunteer", "Oh, no. We told you that you don’t owe anything.", "startled"), d(5.5, 6.5, "Kent", "Please."), d(7, 10, "Volunteer", "I refuse, but with admiration.", "polite"), d(10.5, 14, "Kent", "Please, I respectfully insist.", "desperate but courteous")],
            "first_frame": ref(14, 0), "last_frame": ref(14, 3), "audio": "Quiet mutual-aid center ambience and clear alternating dialogue.",
        },
        {
            "id": "14B", "scene": "Kind Refusal", "duration": 15,
            "action": "The volunteer finally accepts the bracelet and logs it as a return gift, explaining that continued refusal would be rude and saying the group is now indebted to Kent. Kent looks confused and begins walking away. This completes the requested two-generation counter exchange; his internal reaction follows as its own beat.",
            "dialogue": [d(1, 8, "Volunteer", "Well, it would be rude to the mutual-aid group for me to continue to refuse this generous gift.", "overwhelmed"), d(9, 13, "Volunteer", "The mutual-aid group is indebted to you. Thank you.", "sincere")],
            "first_frame": ref(14, 4), "last_frame": ref(14, 6), "audio": "Mutual-aid ambience; Kent's final line is close, dry internal narration rather than moving lips.",
        },
        {
            "id": "14C", "scene": "Kind Refusal — Internal Reaction", "duration": 15,
            "action": "Kent walks away from the mutual-aid counter with a confused, increasingly frustrated expression. His mouth remains closed because the line is internal narration. The volunteer remains behind the counter holding the bracelet.",
            "dialogue": [d(1, 14, "Kent, internal voice", "Indebted? I was indebted to them, and now I’m not, but they’re indebted to me? Why can’t people just accept fucking payments and gifts?!", "frustrated")],
            "first_frame": ref(14, 6), "audio": "Mutual-aid ambience; close internal voice with no lip movement.",
        },
    ],
    18: [
        {
            "id": "18A", "scene": "A Gentle Notice", "duration": 8,
            "action": "Exterior corridor outside Kent's apartment. The housing representative stands near his door speaking politely into her phone. Keep her distinct from every established character.",
            "dialogue": [d(1, 7, "Housing representative", "Before I speak, I want to acknowledge the courage it takes to answer unknown calls.", "carefully empathetic")],
            "first_frame": new_ref("scene_018", 7), "audio": "Quiet apartment corridor ambience and phone-call tone.",
        },
        {
            "id": "18B", "scene": "A Gentle Notice", "duration": 10,
            "action": "Inside Kent's apartment, he leans forward at his desk and answers the phone. His door remains clearly visible behind him. He responds with mild confusion. A peach flower-decorated notice slides under the door; Kent hears it, turns, and raises one eyebrow in astonishment.",
            "dialogue": [d(1, 3, "Kent", "Thanks, I guess.", "slightly confused"), d(4, 9, "Housing representative, through phone", "We recognize relocation can be disruptive.", "compassionate but procedural")],
            "first_frame": ref(18, 0), "last_frame": ref(18, 3), "audio": "Phone voice, paper sliding under a door, quiet apartment room tone.",
        },
        {
            "id": "18C", "scene": "A Gentle Notice", "duration": 8,
            "action": "Return to the housing representative outside Kent's apartment as she delivers the fixed deadline with sincere compassion. She remains on the phone and does not enter.",
            "dialogue": [d(1, 7, "Housing representative", "Your move-out date remains Friday at eight.", "compassionate but procedural")],
            "first_frame": new_ref("scene_018", 7), "audio": "Quiet corridor ambience and phone-call tone.",
        },
        {
            "id": "18D", "scene": "A Gentle Notice", "duration": 7,
            "action": "Back inside, Kent looks at the flower-decorated notice while holding the phone. He understands that the representative is sincere and responds quietly. Hold on the unchanged deadline.",
            "dialogue": [d(2, 5, "Kent", "I believe you.", "quiet")],
            "first_frame": ref(18, 4), "last_frame": ref(18, 6), "audio": "Quiet apartment room tone; call remains connected.",
        },
    ],
    19: [
        {
            "id": "19A", "scene": "Avery's Kitchen", "duration": 12,
            "action": "Video call between Kent's dim apartment and Avery's bright spacious kitchen. Kent keeps the eviction notice outside the camera frame and greets his brother. Avery answers while visibly preoccupied.",
            "dialogue": [d(1, 4.5, "Kent", "Hey, Avery. How are you doing?", "friendly"), d(5, 11.5, "Avery", "Hey, Kent. I’m doing okay. Got a lot going on right now.", "distracted")],
            "first_frame": ref(19, 0), "last_frame": ref(19, 1), "audio": "Natural video-call compression and quiet room tones on both sides.",
        },
        {
            "id": "19B", "scene": "Avery's Kitchen", "duration": 12,
            "action": "Kent begins asking for help, but Avery cuts him off and starts explaining his own obligations. Preserve clean speaker separation across the video call.",
            "dialogue": [d(1, 5, "Kent", "Oh, is this a bad time? I’m needing to—", "hesitant, cut off"), d(5, 11, "Avery", "Look, Kent, I know I said I could help, but the tuition deposit is due Monday.", "interrupting, ashamed")],
            "first_frame": ref(19, 2), "last_frame": ref(19, 3), "audio": "Video-call audio with a natural interruption.",
        },
        {
            "id": "19C", "scene": "Avery's Kitchen", "duration": 12,
            "action": "Stay primarily on Avery in his bright kitchen as he explains that they remortgaged a rental property and Liana's hours were cut. He is sympathetic, not selfish.",
            "dialogue": [d(1, 10, "Avery", "We just had to remortgage one of our rental homes. Liana’s hours got cut. None of this is your fault, but—", "hesitant and ashamed")],
            "first_frame": ref(19, 3), "last_frame": ref(19, 4), "audio": "Quiet kitchen ambience through video-call compression.",
        },
        {
            "id": "19D", "scene": "Avery's Kitchen", "duration": 8,
            "action": "Return to Kent. He stops Avery from defending himself and reassures him. When the call ends, Kent lowers the hidden eviction notice into view.",
            "dialogue": [d(1, 5, "Kent", "You do not have to defend taking care of your family.", "gentle")],
            "first_frame": ref(19, 5), "last_frame": ref(19, 6), "audio": "Video-call end tone followed by Kent's quiet apartment ambience.",
        },
    ],
    20: [
        {"id": "20A", "scene": "Gift Circle", "duration": 8, "action": "Members of Covenant Hall form a circle and give Kent small bills, food, vouchers, and a bus card. Their love is sincere but the total is materially inadequate.", "dialogue": [], "first_frame": ref(20, 0), "last_frame": ref(20, 1), "audio": "Warm murmurs, paper and small gifts changing hands."},
        {"id": "20B", "scene": "Gift Circle", "duration": 9, "action": ACTION["20B"], "dialogue": DIALOGUE["20B"], "first_frame": ref(20, 2), "last_frame": ref(20, 3), "audio": "Room goes quiet after the blurting line; nervous soft murmurs after the correction."},
        {"id": "20C", "scene": "Gift Circle", "duration": 5, "edit_duration": 4, "action": "Reaction insert: several members' eyes shift left and right, checking whether everyone accepted the corrected explanation. Their smiles are strained but nobody speaks. Hold a clean four-second usable reaction within the five-second generation.", "dialogue": [], "first_frame": ref(20, 4), "audio": "Awkward room tone and a tiny clothing rustle."},
        {"id": "20D", "scene": "Gift Circle", "duration": 5, "edit_duration": 4, "action": "Reaction close-up on Kent: initial astonished hope when he hears this isn't enough, as if someone finally understands the structural problem. Hold a clean four-second usable reaction within the five-second generation.", "dialogue": [], "first_frame": ref(20, 3), "audio": "Muted room ambience."},
        {"id": "20E", "scene": "Gift Circle", "duration": 5, "edit_duration": 4, "action": "Kent realizes the member only meant the gift did not express enough care. He exhales deeply in frustration and returns to writing down how to repay everyone. Hold a clean four-second usable reaction within the five-second generation.", "dialogue": [], "first_frame": ref(20, 5), "last_frame": ref(20, 6), "audio": "Deep sigh, pencil on paper, low room murmur."},
    ],
    24: [
        {"id": "24A", "scene": "Equal Time", "duration": 8, "action": ACTION["24A"], "dialogue": [], "first_frame": ref(24, 0), "last_frame": ref(24, 1), "audio": "Quiet council-room ambience and polite settling."},
        {"id": "24B", "scene": "Equal Time", "duration": 15, "action": "Ryann at the podium tells the room all voices deserve equal time and warmth, then turns to Kent and thanks him for returning. She faces the audience again to introduce his statement.", "dialogue": [d(0.5, 4, "Ryann Sally", "All voices deserve equal time and equal warmth.", "welcoming"), d(4.2, 7.5, "Ryann Sally", "Mr. Brentwood, thank you for returning.", "turning to Kent"), d(7.7, 15, "Ryann Sally", "Mr. Brentwood has asked for the floor to present a statement pertaining to what we all hold near and dear.", "to the room")], "first_frame": ref(24, 2), "last_frame": ref(24, 3), "audio": "Clear podium microphone and restrained room tone."},
        {"id": "24C", "scene": "Equal Time", "duration": 15, "action": "Ryann slowly says Universal Equality with a slight British accent. She explains that she will first open the floor for nice remarks before Kent's criticism, then gulps nervously on the difficult word.", "dialogue": [d(1, 4, "Ryann Sally", "Universal Equality.", "slow, slight British accent"), d(4.5, 13.5, "Ryann Sally", "First, though, I will be opening the floor to anyone who would just like to say something nice before Mr. Brentwood presents his—criticism.", "growing nervous and gulping before criticism")], "first_frame": ref(24, 3), "last_frame": ref(24, 4), "audio": "Podium microphone; tiny nervous breath before criticism."},
        {"id": "24D", "scene": "Equal Time", "duration": 12, "action": "Ryann looks toward Kent with confused concern, realizes there may be several criticisms, gathers composure, opens the floor, and walks away from the podium.", "dialogue": [d(1, 5, "Ryann Sally", "Criticisms? Plural?", "questioning Kent, worried"), d(6, 10, "Ryann Sally", "Well then, the floor is now open.", "regaining composure")], "first_frame": ref(24, 4), "last_frame": ref(24, 6), "audio": "Quiet council-room ambience, footsteps away from podium."},
    ],
    25: [
        {"id": "25A", "scene": "Testimonies", "duration": 15, "action": "Avery speaks from the full podium to the council, sincerely saying he loves Kent, wants to help, and knows Kent needs help. He carefully describes Kent as being in a slump.", "dialogue": [d(1, 14, "Avery", "I love my brother. I want to help him. I know he needs help. He has been in a—slump of sorts.", "sincere and conflicted")], "first_frame": ref(25, 0), "last_frame": ref(25, 1), "audio": "Clear podium microphone and silent attentive room."},
        {"id": "25B", "scene": "Testimonies", "duration": 15, "action": "Avery continues, speaking to the crowd about the inevitable slump and sacrifices made for Universal Equality. He ends by looking down toward Kent in genuine concern while suggesting Kent may be weak in this area.", "dialogue": [d(1, 14, "Avery", "When most of us go through the inevitable slump, most of us stay strong and know what we must sacrifice to preserve our right to Universal Equality. But my brother, though very strong, may in fact be weak in this area.", "earnest, ending with concern for Kent")], "first_frame": ref(25, 1), "last_frame": ref(25, 2), "audio": "Podium microphone, no audience interruption."},
        {"id": "25C", "scene": "Testimonies", "duration": 10, "action": "Faith White explains the religious principle supporting household protection. She is sincere and calm.", "dialogue": [d(1, 9, "Faith White", "Giving should not destroy the giver’s nearest circle. That is not a shield against compassion. It is a guardrail against collapse.", "calm")], "first_frame": ref(25, 3), "last_frame": ref(25, 4), "audio": "Clear room microphone."},
        {"id": "25D", "scene": "Testimonies", "duration": 8, "action": "Ryann explains that unequal aid could imply unequal worth, then resets the sand timer for Kent.", "dialogue": [d(1, 6, "Ryann Sally", "Unequal aid can imply unequal worth. We protect equal regard.", "assured")], "first_frame": ref(25, 5), "last_frame": ref(25, 6), "audio": "Microphone and a small sand-timer movement."},
    ],
    26: [
        {"id": "26A", "scene": "The Sentence", "duration": 8, "action": "Kent stands at the microphone gripping the full podium while everyone watches kindly. He gathers courage before speaking.", "dialogue": [], "first_frame": ref(26, 0), "last_frame": ref(26, 1), "audio": "Near-silent council room and one steady breath."},
        {"id": "26B", "scene": "The Sentence", "duration": 10, "action": "Kent states that everyone was kind to him and then clearly names the outcome as unfair. Let the word unfair land without interruption.", "dialogue": [d(1, 4, "Kent", "Everyone was kind to me.", "steady"), d(5, 9, "Kent", "This is still unfair.", "direct")], "first_frame": ref(26, 1), "last_frame": ref(26, 2), "audio": "Clear podium microphone and silent room."},
        {"id": "26C", "scene": "The Sentence", "duration": 15, "action": "Kent addresses the room, acknowledges Avery is not wrong, and describes himself as being in a slump, making visible air quotes around slump. He firmly rejects being called weak.", "dialogue": [d(1, 14, "Kent", "Hello, everyone. My brother is not wrong. I am going through a ‘slump’—though I would not say I’m weak.", "matter-of-fact, air quotes around slump")], "first_frame": ref(26, 2), "last_frame": ref(26, 3), "audio": "Podium microphone; no audience reaction yet."},
        {"id": "26D", "scene": "The Sentence", "duration": 15, "action": "Kent explains that many people suffer repeated slumps in service of others, and that those who fulfill civic duty most faithfully are punished worst. He pauses and looks down with concern before looking back up.", "dialogue": [d(1, 14, "Kent", "Like many others, I have had many slumps in my life in the service of others. Sometimes those slumps feel like trenches. The ones among us who fulfill our civic duty the best get punished the worst.", "growing conviction")], "first_frame": ref(26, 3), "last_frame": ref(26, 4), "audio": "Quiet council room and clear speech."},
        {"id": "26E", "scene": "The Sentence", "duration": 15, "action": "Kent says society rejected the old dog-eat-dog world and mistakenly believed equal treatment would fix inequality. Keep his frustration controlled.", "dialogue": [d(1, 14, "Kent", "We got here by all agreeing that the old ways of a dog-eat-dog world don’t work. We thought treating each other equally would fix inequality, but nothing has changed. We still have the rich and the poor.", "controlled frustration")], "first_frame": ref(26, 4), "last_frame": ref(26, 5), "audio": "Podium microphone; audience remains silent."},
        {"id": "26F", "scene": "The Sentence", "duration": 15, "action": "Kent contrasts the most generous citizens giving the most with the least generous still having the most. His frustration becomes visible but never violent or cruel.", "dialogue": [d(1, 13, "Kent", "The only difference now is the most generous among us gives the most willingly, while the least generous ones still—have the most! We can fix this. I don’t know who thought this was a good idea.", "frustrated")], "first_frame": ref(26, 5), "last_frame": ref(26, 6), "audio": "Podium microphone and a few uneasy breaths from the room."},
        {"id": "26G", "scene": "The Sentence", "duration": 9, "action": "Kent starts mentioning Karl Marx. Cut to the last sand falling through the hourglass and Ryann watching impatiently. She strikes the gavel once and interrupts him sternly.", "dialogue": [d(1, 3, "Kent", "There’s this guy, Karl Mar—", "cut off"), d(5, 8, "Ryann Sally", "Thank you, Mr. Brentwood, but your time is up.", "stern")], "first_frame": ref(24, 4), "last_frame": ref(26, 6), "audio": "Last grains of sand, one sharp gavel strike, then silence."},
    ],
    27: [
        {"id": "27A", "scene": "Compassionate Response", "duration": 10, "action": "Ryann responds with visible discomfort, hesitating over Kent's hard words before validating his experience of unfairness.", "dialogue": [d(1, 5, "Ryann Sally", "Kent, thank you for trusting us with—um—those hard words.", "gentle but unsettled"), d(5.5, 9, "Ryann Sally", "We validate that your experience of unfairness is real.", "recovering")], "first_frame": ref(27, 0), "last_frame": ref(27, 1), "audio": "Council microphone and careful pauses."},
        {"id": "27B", "scene": "Compassionate Response", "duration": 9, "action": "Ryann explains with sincere procedural concern that changing the rule for one applicant could imply that other applicants have less dignity.", "dialogue": [d(1, 8, "Ryann Sally", "Changing the equal-grant rule for one applicant could imply that other applicants’ needs carry less civic dignity.", "caring but procedural")], "first_frame": ref(27, 2), "last_frame": ref(27, 3), "audio": "Clear council microphone."},
        {"id": "27C", "scene": "Compassionate Response", "duration": 7, "action": "A council support person offers Kent a tissue box. Kent looks at Ryann in incredulous frustration, then declines the tissues with a firm head shake and one hand. He does not cry; he wants reform, not consolation.", "dialogue": [], "first_frame": ref(27, 3), "last_frame": ref(27, 4), "audio": "Awkward room silence and a small tissue-box movement."},
        {"id": "27D", "scene": "Compassionate Response", "duration": 8, "action": "Kent tries to challenge Ryann. She immediately bangs the gavel again and sternly says his time is over. Kent is frustrated but remains physically controlled.", "dialogue": [d(1, 3, "Kent", "But Ryann, did you—", "trying to interject"), d(4, 8, "Ryann Sally", "Mr. Brentwood, your time is up. You have made your statement.", "stern")], "first_frame": ref(27, 4), "last_frame": ref(27, 5), "audio": "One gavel strike interrupts Kent."},
        {"id": "27E", "scene": "Compassionate Response", "duration": 10, "action": "Before Kent can respond, a council member motions to assign him a support liaison. Kent asks whether he is still being removed from his home. Ryann softly confirms yes.", "dialogue": [d(1, 4, "Council member", "I motion that Kent be assigned a support liaison."), d(4.5, 7, "Kent", "Will the next step be moving out?", "practical"), d(8, 9, "Ryann Sally", "Yes.", "soft")], "first_frame": ref(27, 5), "last_frame": ref(27, 6), "audio": "Council-room ambience and clear separated speakers."},
    ],
}


def reference_block(first: str, last: str | None) -> str:
    if last:
        return (
            "<Picture 1> is the opening visual anchor and <Picture 2> is the closing visual anchor. "
            "Preserve identity, wardrobe, props, geography, lighting, and screen direction; move naturally between them without a cut or morph. "
        )
    return (
        "<Picture 1> is the sole visual anchor. Preserve its identities, wardrobe, props, lighting, and location; "
        "continue naturally without inventing an unrelated endpoint. "
    )


def prompt_for(spec: dict, character_block: str) -> str:
    dialogue = spec.get("dialogue", [])
    if dialogue:
        dialogue_text = " ".join(f"[{x['start']:g}s-{x['end']:g}s] {x['label']}" for x in dialogue)
    else:
        dialogue_text = "No dialogue. Preserve quiet natural performance."
    return (
        f"Standard MiniMax H3 reference-to-video, full-quality non-Turbo, {spec['duration']} seconds, 16:9, one continuous shot with no internal edit. "
        + reference_block(spec["first_frame"], spec.get("last_frame"))
        + f"Character continuity: {character_block}. "
        + f"Scene and performance: {spec['action']} "
        + "Movement must be physically plausible and emotionally specific. Keep each speaker's mouth closed outside their assigned line. "
        + f"Dialogue timing: {dialogue_text} "
        + f"Synchronized audio: {spec.get('audio', 'Natural location ambience and clear dialogue.')} "
        + "No subtitles, captions, visible prompt text, logos, watermarks, identity drift, duplicate people, glass barriers, or Turbo generation."
    )


def character_block_for(spec: dict, old_prompt: str = "") -> str:
    if spec["id"].startswith("00"):
        if spec["id"] in {"00J"}:
            return KENT
        if spec["id"] in {"00K", "00L", "00M", "00N", "00O"}:
            return f"{KENT}; {NARRATOR}"
        return (
            NARRATOR
            + "; Male Visitor One and Male Visitor Two are distinct adult men and remain the same two public-side waiting-room visitors across every monochrome shot"
            + "; the middle-aged woman receptionist remains the same third person and stays entirely behind the staff-only check-in window"
            + "; the open entrance doorway is a separate architectural opening at far screen-right"
        )
    cid = spec["id"]
    if cid == "13B":
        return f"{KENT}; {DORIS}"
    if cid in {"14A", "14B", "14C"}:
        return f"{KENT}; {VOLUNTEER}"
    if cid in {"16D", "16E", "16F"}:
        return KENT
    if cid == "16G":
        return f"{KENT}; {RYANN}"
    if cid in {"18A", "18C"}:
        return HOUSING_REP
    if cid in {"18B", "18D"}:
        return KENT
    if cid.startswith("19"):
        return f"{KENT}; {AVERY}"
    if cid.startswith("24"):
        return f"{KENT}; {RYANN}"
    if cid in {"25A", "25B"}:
        return f"{AVERY}; {KENT} remains the exact established audience listener"
    if cid == "25C":
        return FAITH
    if cid == "25D":
        return RYANN
    if cid == "26G":
        return f"{KENT}; {RYANN}"
    if cid.startswith("27"):
        return f"{KENT}; {RYANN}; preserve the established council members from the selected reference"
    match = re.search(r"Character continuity: (.*?)\. Action and performance:", old_prompt)
    return match.group(1) if match else KENT


def convert_dialogue(items: list[dict]) -> list[dict]:
    return [{"start": x["start"], "end": x["end"], "line": x["label"]} for x in items]


def make_clip(spec: dict, old: dict | None, sequence: int, global_negative: str) -> dict:
    first = spec.get("first_frame") or (old or {}).get("first_frame")
    last = spec.get("last_frame", (old or {}).get("last_frame"))
    if not first:
        raise ValueError(f"{spec['id']}: missing first frame")
    normalized = {**spec, "first_frame": first, "last_frame": last}
    chars = character_block_for(normalized, (old or {}).get("prompt", ""))
    negative = (old or {}).get("negative_prompt", global_negative)
    return {
        "id": normalized["id"],
        "scene": normalized.get("scene", (old or {}).get("scene", "")),
        "sequence_order": sequence,
        "prompt": prompt_for(normalized, chars),
        "negative_prompt": negative,
        "first_frame": first,
        **({"last_frame": last} if last else {}),
        "duration": normalized["duration"],
        "edit_duration": normalized.get("edit_duration", normalized["duration"]),
        "frames": h3_frames(normalized["duration"]),
        "fps": 24,
        "seed": 64000 + sequence,
        "dialogue_timing": convert_dialogue(normalized.get("dialogue", [])),
        "audio": normalized.get("audio", "Natural location ambience and clear dialogue."),
        "validation_plan": f"validation_revised/clip_{normalized['id']}.json",
        "revision_source": "author contextual rewrite 2026-08-09",
        "action": normalized["action"],
    }


def base_spec(old: dict, source: dict) -> dict:
    clip_id = old["id"]
    return {
        "id": clip_id,
        "scene": old.get("scene", ""),
        "duration": DURATION.get(clip_id, int(old["duration"])),
        "action": ACTION.get(clip_id, source.get("source_prompt", old.get("prompt", ""))),
        "dialogue": DIALOGUE.get(clip_id, [
            {
                "start": x["start"], "end": x["end"],
                "speaker": x["line"].split(":", 1)[0], "delivery": "",
                "line": x["line"].split(": “", 1)[-1].rstrip("”"), "label": x["line"],
            }
            for x in old.get("dialogue_timing", [])
        ]),
        "first_frame": old.get("first_frame"),
        "last_frame": old.get("last_frame"),
        "audio": old.get("audio", "Natural location ambience."),
    }


def additional_overrides(spec: dict) -> dict:
    cid = spec["id"]
    if cid == "16C":
        spec.update({"duration": 6, "action": "Kent pauses at the full podium after saying people have unequal needs, then prepares to elaborate. Hold the confused but attentive room in silence.", "dialogue": [], "first_frame": new_ref("scene_016", 7), "last_frame": None})
    elif cid == "21C":
        spec.update({"duration": 10, "action": ACTION["21C"], "first_frame": new_ref("scene_021", 7), "last_frame": None, "audio": "Original melancholy cartoon-like solo piano and soft woodwind cue; do not imitate or quote any recognizable Snoopy or Peanuts music."})
    elif cid == "30C":
        spec.update({"duration": 10, "action": ACTION["30C"], "first_frame": new_ref("scene_030", 7), "last_frame": None, "audio": "Warm evening city ambience and restrained original closing music, fading to silence."})
    elif cid == "06C":
        spec.update({"duration": 10, "action": ACTION["06C"], "first_frame": ref(6, 4), "last_frame": new_ref("scene_006", 7)})
    elif cid == "13B":
        spec.update({"first_frame": new_ref("scene_013", 7), "last_frame": None})
    elif cid == "22B":
        spec.update({"duration": 15, "dialogue": [d(1, 14, "Doris recording", "Equal shares. Equal love. No one should be hurt by wondering who mattered more. If either of you needs more, I trust you will be kind to each other.", "warm and trusting")]})
    return spec


def validation_record(clip: dict) -> dict:
    critical = []
    if clip["id"].startswith("00"):
        critical.append("prologue remains black-and-white until 00J; waiting room contains exactly one chair")
    if clip["id"] in {"00A", "00B", "00C", "00D", "00D2", "00E", "00F", "00G", "00H", "00I"}:
        critical.extend([
            "woman receptionist remains the only person behind the staff-only check-in window",
            "both waiting-room visitors are men and remain entirely in the public room",
            "reception window and open entrance doorway remain separate; no glass gate or fence",
        ])
    if clip["id"] == "06C":
        critical.append("invoice reads OAK GROVE RETIREMENT HOME and $6,76,767 exactly")
    if clip["id"] == "13B":
        critical.append("one thought bubble contains a photorealistic Doris-and-Kent flashback; no text bubble")
    if clip["id"] in {"16B", "16C", "16D", "16E", "16F", "16G"}:
        critical.append("full podium and consistent council-room geography; preserve open Ryann approach path")
    if clip["id"] == "21C":
        critical.append("strict side-on left-to-right walk; music is original and does not quote Peanuts/Snoopy")
    if clip["id"] == "30C":
        critical.append("rear view walking into sunset, then clean fade-to-black handle")
    return {
        "clip_id": clip["id"],
        "duration_seconds": clip["duration"],
        "required_story_action": clip["action"],
        "dialogue_timing": clip["dialogue_timing"],
        "references": {"first": clip["first_frame"], "last": clip.get("last_frame")},
        "critical_checks": critical,
        "checks": {
            "story_action_complete": None,
            "dialogue_exact_and_correct_speaker": None,
            "dialogue_fits_without_rushing": None,
            "identity_and_wardrobe_consistent": None,
            "location_and_screen_direction_consistent": None,
            "no_unrequested_barrier_or_glass_gate": None,
            "audio_clean_and_synchronized": None,
            "technical_video_valid": None,
        },
        "decision": {"status": "pending", "retry_reason": ""},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("revision", type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    revision = args.revision.resolve()
    config_path = project / "story_config.json"
    shot_path = project / "shot_plan.json"
    source_path = project / "source_clip_script.json"
    backup_config = project / "story_config_pre_contextual_revision.json"
    backup_shot = project / "shot_plan_pre_contextual_revision.json"
    base_config_path = backup_config if backup_config.exists() else config_path
    current_config = json.loads(config_path.read_text(encoding="utf-8"))
    config = json.loads(base_config_path.read_text(encoding="utf-8"))
    config.update({key: value for key, value in current_config.items() if key != "clips"})
    old_clips = config["clips"]
    old_by_id = {x["id"]: x for x in old_clips}
    source_data = json.loads(source_path.read_text(encoding="utf-8"))
    source_by_id = {x["id"]: x for scene in source_data["scenes"] for x in scene["clips"]}

    output_specs = copy.deepcopy(PROLOGUE)
    replaced_scenes = set(REPLACEMENT_SCENES)
    seen_replaced = set()
    for old in old_clips:
        scene_number = int(old["id"][:2])
        if scene_number in replaced_scenes:
            if scene_number not in seen_replaced:
                seen_replaced.add(scene_number)
                for item in copy.deepcopy(REPLACEMENT_SCENES[scene_number]):
                    output_specs.append(item)
                if scene_number == 14:
                    output_specs.extend(copy.deepcopy(INSERT_AFTER["14C"]))
            continue
        spec = additional_overrides(base_spec(old, source_by_id.get(old["id"], {})))
        output_specs.append(spec)
        output_specs.extend(copy.deepcopy(INSERT_AFTER.get(old["id"], [])))

    global_negative = config.get("negative_prompt", "")
    revised = [make_clip(spec, old_by_id.get(spec["id"]), index, global_negative) for index, spec in enumerate(output_specs, 1)]
    total = sum(x["duration"] for x in revised)
    editorial_total = sum(x["edit_duration"] for x in revised)

    if not backup_config.exists():
        backup_config.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
    if not backup_shot.exists():
        backup_shot.write_text(shot_path.read_text(encoding="utf-8"), encoding="utf-8")

    config["clips"] = revised
    config["author_revision_source"] = revision.name
    config["planned_runtime_seconds"] = total
    config["planned_runtime"] = f"{total // 60}:{total % 60:02d}"
    config["planned_editorial_runtime_seconds"] = editorial_total
    config["planned_editorial_runtime"] = f"{editorial_total // 60}:{editorial_total % 60:02d}"
    config["schema_version"] = 3
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    bible_path = project / "story_bible.json"
    bible_backup = project / "story_bible_pre_contextual_revision.json"
    if not bible_backup.exists():
        bible_backup.write_text(bible_path.read_text(encoding="utf-8"), encoding="utf-8")
    bible = json.loads(bible_path.read_text(encoding="utf-8"))
    bible["project"].update({
        "target_minutes": round(editorial_total / 60, 2),
        "target_seconds": editorial_total,
        "target_shots": len(revised),
        "clip_duration_range_seconds": [min(x["duration"] for x in revised), max(x["duration"] for x in revised)],
        "source_script": revision.name,
        "content_rating": "R for one strong expletive in Kent's internal monologue",
        "opening_requirement": "Black-and-white anthology-TV prologue in a sterile one-chair waiting room, followed by the Narrator introducing Kent and naming the Super Nice Zone.",
    })
    if not any(x.get("id") == "narrator" for x in bible["characters"]):
        bible["characters"].append({
            "id": "narrator", "name": "The Narrator", "role": "on-screen prologue host and off-screen guide",
            "appearance": NARRATOR, "motivation": "frame the equality paradox without resolving it",
            "reference_images": ["frames/scene_000/boundary_00_v2.png", "frames/scene_000/boundary_04_v2.png", "frames/scene_000/boundary_05.png"],
        })
    bible_path.write_text(json.dumps(bible, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    shot_plan = {
        "schema_version": 3,
        "source_script": revision.name,
        "project": {"title": "Equal Shares", "clip_count": len(revised), "generation_seconds": total, "generation_runtime": f"{total // 60}:{total % 60:02d}", "editorial_seconds": editorial_total, "editorial_runtime": f"{editorial_total // 60}:{editorial_total % 60:02d}", "generation_model": "MiniMax H3 full quality non-Turbo"},
        "editorial_rules": [
            "Long dialogue is divided at sentence boundaries and performed at a natural pace.",
            "The black-and-white prologue uses a vintage anthology-TV visual grammar without copying protected music or a specific host likeness.",
            "Hard cuts occur between clips; each generated clip remains one continuous shot.",
            "The Scene 14 exchange uses two 15-second generations as requested.",
        ],
        "clips": revised,
    }
    shot_path.write_text(json.dumps(shot_plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (project / "AUTHOR_CONTEXTUAL_REVISION.txt").write_text(revision.read_text(encoding="utf-8-sig"), encoding="utf-8")

    validation_dir = project / "validation_revised"
    validation_dir.mkdir(exist_ok=True)
    for clip in revised:
        (validation_dir / f"clip_{clip['id']}.json").write_text(json.dumps(validation_record(clip), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Equal Shares — Revised Generation Plan", "",
        f"- Clips: {len(revised)}", f"- Generated footage runtime: {total // 60}:{total % 60:02d}", f"- Planned editorial runtime: {editorial_total // 60}:{editorial_total % 60:02d}",
        "- Model: MiniMax H3 full quality, non-Turbo", "",
    ]
    current_scene = None
    for clip in revised:
        if clip["scene"] != current_scene:
            current_scene = clip["scene"]
            lines.extend([f"## {current_scene}", ""])
        refs = clip["first_frame"] + (f" → {clip['last_frame']}" if clip.get("last_frame") else " (single anchor)")
        edit_note = f"; use {clip['edit_duration']}s in edit" if clip["edit_duration"] != clip["duration"] else ""
        lines.extend([f"### {clip['id']} — generate {clip['duration']}s / {clip['frames']} frames{edit_note}", "", clip["action"], "", f"References: `{refs}`", ""])
        for timing in clip["dialogue_timing"]:
            lines.append(f"- {timing['start']:g}–{timing['end']:g}s: {timing['line']}")
        lines.append("")
    (project / "REVISED_GENERATION_PLAN.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Revised plan: {len(revised)} clips, generate {total // 60}:{total % 60:02d}, edit {editorial_total // 60}:{editorial_total % 60:02d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
