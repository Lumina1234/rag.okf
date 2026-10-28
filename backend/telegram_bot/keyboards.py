"""Reply keyboards and inline menus for the Telegram bot."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["📤 Upload PDF", "📥 Download PDF"],
            ["❓ Ask Question", "📝 Summary"],
            ["⭐ Important Questions", "📋 PYQs"],
            ["🧪 Generate Quiz", "📚 Subjects"],
            ["❓ Help"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def subject_keyboard(subjects: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            f"{'📗' if i % 2 == 0 else '📘'} {s['name']}",
            callback_data=f"subject:{s['id']}",
        )]
        for i, s in enumerate(subjects)
    ]
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)


def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 Q&A", callback_data="mode:qa"),
            InlineKeyboardButton("📄 Summary", callback_data="mode:summary"),
        ],
        [
            InlineKeyboardButton("⭐ Important Qs", callback_data="mode:important_questions"),
            InlineKeyboardButton("🎓 VTU Answer", callback_data="mode:vtu"),
        ],
        [
            InlineKeyboardButton("🧒 Simple Explain", callback_data="mode:simple"),
            InlineKeyboardButton("🧪 Quiz", callback_data="mode:quiz"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])


def category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📓 Notes", callback_data="cat:notes"),
            InlineKeyboardButton("📋 PYQ", callback_data="cat:pyq"),
        ],
        [
            InlineKeyboardButton("🔬 Lab Manual", callback_data="cat:lab"),
            InlineKeyboardButton("📖 Textbook", callback_data="cat:textbook"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]])


def scheme_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("2022 Scheme", callback_data="set_scheme:2022"),
            InlineKeyboardButton("2025 Scheme", callback_data="set_scheme:2025"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])


def branch_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("CSE", callback_data="set_branch:CSE"),
            InlineKeyboardButton("ISE", callback_data="set_branch:ISE"),
        ],
        [
            InlineKeyboardButton("AI&DS", callback_data="set_branch:AI_DS"),
            InlineKeyboardButton("AI&ML", callback_data="set_branch:AI_ML"),
            InlineKeyboardButton("ECE", callback_data="set_branch:ECE"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu")],
    ])


def semester_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for i in range(1, 9, 2):
        buttons.append([
            InlineKeyboardButton(f"Sem {i}", callback_data=f"set_sem:{i}"),
            InlineKeyboardButton(f"Sem {i+1}", callback_data=f"set_sem:{i+1}"),
        ])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


def subject_dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 Upload PDF", callback_data="action:upload"),
            InlineKeyboardButton("📥 Download PDF", callback_data="action:download"),
        ],
        [InlineKeyboardButton("🧠 Ask AI", callback_data="action:ask_ai")],
        [InlineKeyboardButton("📄 Previous Papers", callback_data="action:pyq"), InlineKeyboardButton("📑 Syllabus", callback_data="action:syllabus")],
        [InlineKeyboardButton("🎯 Important Questions", callback_data="action:imp_q"), InlineKeyboardButton("📝 Lab Manual", callback_data="action:lab")],
        [InlineKeyboardButton("⬅️ Change Subject", callback_data="menu")],
    ])


def answer_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 Short Definition", callback_data="ans_type:short"),
            InlineKeyboardButton("📖 Detailed Explanation", callback_data="ans_type:detailed"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])


def pdf_list_keyboard(pdfs: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"📄 {p['original_name'][:40]}", callback_data=f"dl_pdf:{p['id']}")] for p in pdfs
    ]
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="action:back")])
    return InlineKeyboardMarkup(buttons)
