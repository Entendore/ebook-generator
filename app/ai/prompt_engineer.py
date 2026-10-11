"""Prompt engineering system for all ebook types.

This module provides specialized prompt templates and construction logic
for every supported ebook genre. Each type has tailored system prompts,
chapter generation prompts, outline prompts, and post-processing prompts.

The PromptEngineer assembles prompts from templates + project context
to produce optimal inputs for the LLM at each stage of generation.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..models.book_project import EbookType, BookProject, Chapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Base system prompts per ebook type
# ---------------------------------------------------------------------------

BASE_SYSTEM_PROMPTS: dict[EbookType, str] = {
    EbookType.FICTION_NOVEL: (
        "You are a masterful fiction writer with decades of experience crafting "
        "compelling novels. You write vivid, immersive prose with deep character "
        "development, natural dialogue, and richly layered narratives. You maintain "
        "consistent tone, voice, and style throughout the entire book. You understand "
        "story structure — rising action, climaxes, and satisfying resolutions. "
        "You show rather than tell, using sensory details and subtext."
    ),
    EbookType.SHORT_STORIES: (
        "You are an acclaimed short story writer known for powerful, concise "
        "narratives. Each story you write has a complete arc within a compact "
        "form — a strong opening hook, meaningful middle, and resonant ending. "
        "You use precise language, every sentence earning its place. You excel "
        "at creating vivid characters and settings in minimal space."
    ),
    EbookType.NON_FICTION_GUIDE: (
        "You are an expert non-fiction author who writes clear, engaging, and "
        "authoritative guides. You organize complex information into logical, "
        "easy-to-follow structures. You use practical examples, analogies, and "
        "real-world case studies to illustrate concepts. You write in an "
        "accessible yet knowledgeable tone that respects the reader's intelligence."
    ),
    EbookType.TECHNICAL_BOOK: (
        "You are a senior software engineer and technical author who writes "
        "programming books that are both accurate and approachable. You include "
        "working code examples, explain concepts from first principles, and "
        "progress from beginner to advanced topics. You use consistent code "
        "style, clear explanations, and practical exercises."
    ),
    EbookType.SELF_HELP: (
        "You are a bestselling self-help author who blends research-backed "
        "insights with compelling personal stories. You write with empathy and "
        "authority, providing actionable frameworks, exercises, and step-by-step "
        "guidance. You motivate readers while being honest about challenges. "
        "Your writing is warm, direct, and transformation-oriented."
    ),
    EbookType.COOKBOOK: (
        "You are a professional chef and cookbook author. You write recipes that "
        "are precise, tested, and easy to follow. You include helpful tips, "
        "variation suggestions, and cultural context for dishes. You organize "
        "chapters by meal type, cuisine, or ingredient, with clear ingredient "
        "lists, step-by-step instructions, and serving suggestions."
    ),
    EbookType.CHILDREN_BOOK: (
        "You are a children's book author who writes engaging, age-appropriate "
        "content. You use simple but vivid language, create memorable characters, "
        "and weave in gentle lessons or themes. Your stories capture children's "
        "imagination while being accessible to young readers."
    ),
    EbookType.POETRY_COLLECTION: (
        "You are an accomplished poet with mastery over multiple forms — "
        "free verse, sonnets, haiku, villanelles, and more. You write with "
        "musicality, vivid imagery, emotional depth, and precise word choice. "
        "Each poem stands alone while contributing to the collection's themes."
    ),
    EbookType.TEXTBOOK: (
        "You are a professor and textbook author who presents academic material "
        "with clarity and rigor. You structure content with learning objectives, "
        "key terms, examples, summaries, and review questions. You balance "
        "theoretical depth with practical accessibility for students."
    ),
    EbookType.MEMOIR_BIOGRAPHY: (
        "You are a skilled biographer and memoir writer who brings lives to "
        "the page with vivid scenes, dialogue, and emotional truth. You weave "
        "chronological narrative with thematic reflection, balancing factual "
        "accuracy with compelling storytelling."
    ),
    EbookType.BUSINESS_BOOK: (
        "You are a business strategist and author who writes insightful, "
        "data-informed books on leadership, strategy, and innovation. You "
        "combine frameworks, case studies, and actionable takeaways. Your "
        "writing is sharp, persuasive, and grounded in real-world experience."
    ),
    EbookType.SCIFI_FANTASY: (
        "You are a bestselling science fiction and fantasy author who builds "
        "immersive worlds with consistent internal logic. You craft complex "
        "magic systems or technologies, diverse characters, and epic story "
        "arcs. You balance world-building exposition with forward-moving plot."
    ),
    EbookType.MYSTERY_THRILLER: (
        "You are a master of mystery and thriller fiction. You plant clues "
        "fairly, maintain suspense throughout, create twists that surprise "
        "but satisfy, and build psychological tension. Your pacing is precise — "
        "fast when it needs to be, slow for character moments."
    ),
    EbookType.ROMANCE: (
        "You are a bestselling romance author who creates compelling love "
        "stories with emotional depth, relatable characters, and satisfying "
        "romantic arcs. You balance tension and tenderness, write authentic "
        "dialogue, and create chemistry between characters that feels genuine."
    ),
    EbookType.HISTORICAL_FICTION: (
        "You are a historical fiction author who brings past eras to life "
        "with meticulous research and vivid storytelling. You weave real "
        "historical events and figures into compelling fictional narratives. "
        "Your prose captures the language, customs, and atmosphere of the period."
    ),
}

# ---------------------------------------------------------------------------
# Contextual modifiers appended to system prompts
# ---------------------------------------------------------------------------

CONTEXT_MODIFIERS = {
    "tone_formal": "\n\nTone: Formal, academic, and authoritative.",
    "tone_casual": "\n\nTone: Conversational, friendly, and approachable.",
    "tone_dramatic": "\n\nTone: Dramatic, intense, and emotionally charged.",
    "tone_warm": "\n\nTone: Warm, personal, and encouraging.",
    "tone_technical": "\n\nTone: Precise, technical, and detail-oriented.",
    "no_cliches": "\n\nIMPORTANT: Avoid cliches, overused phrases, and generic language. Be original and specific.",
    "show_dont_tell": "\n\nIMPORTANT: Show, don't tell. Use vivid sensory details, action, and dialogue rather than stating emotions or facts flatly.",
    "sensory_rich": "\n\nIMPORTANT: Use rich sensory language — sight, sound, smell, touch, taste — to create immersive scenes.",
    "research_backed": "\n\nInclude references to research, studies, and data where appropriate to support claims.",
    "practical_exercises": "\n\nInclude practical exercises, worksheets, or reflection prompts at the end of major sections.",
}

# ---------------------------------------------------------------------------
# Stage-specific prompt builders
# ---------------------------------------------------------------------------

OUTLINE_PROMPT_TEMPLATE = """Generate a detailed chapter-by-chapter outline for the following book.

Book Title: {title}
Book Type: {ebook_type_label}
Description: {description}
Target Audience: {target_audience}
Number of Chapters: {total_chapters}
Approximate Words per Chapter: {words_per_chapter}

{additional_instructions}

For each chapter, provide:
1. Chapter number and title
2. A 2-3 sentence synopsis of what happens / what is covered
3. Key characters, concepts, or themes introduced
4. How it connects to the previous and next chapter

Format as a numbered list with clear chapter headings."""

CHAPTER_GENERATION_TEMPLATE = """You are writing Chapter {chapter_num} of "{book_title}" by {author}.

{system_context}

**Chapter Title:** {chapter_title}
**Chapter Synopsis:** {chapter_synopsis}

{previous_chapter_summary}

{outline_context}

**Instructions:**
- Write approximately {target_words} words
- Maintain consistency with the overall book outline and style
- {chapter_specific_instructions}
- Begin the chapter naturally (no meta-commentary about writing)
- End at a natural break point or chapter boundary

Write the full chapter now:"""

FRONTMATTER_PROMPT = """Generate professional front matter for the book "{title}" by {author}.

Book Type: {ebook_type_label}
Description: {description}

Include the following elements in order:
1. Title page content (title, subtitle, author)
2. A compelling foreword or preface (1-2 pages)
3. Table of Contents placeholder

{dedication_section}
{custom_frontmatter}

Write the front matter now:"""

BACKMATTER_PROMPT = """Generate professional back matter for the book "{title}" by {author}.

Book Type: {ebook_type_label}
Description: {description}
Number of Chapters: {num_chapters}

Include:
1. An afterword or conclusion that ties the book together
2. Acknowledgments section
3. An "About the Author" section (2-3 paragraphs)

{custom_backmatter}

Write the back matter now:"""

CHAPTER_SUMMARY_TEMPLATE = """Summarize the following chapter in 3-5 concise sentences, focusing on:
- Key plot points or main arguments
- Important character developments or concept introductions
- How this chapter connects to the overall narrative arc

Chapter: {chapter_title}
Content:
{chapter_content}

Summary:"""


class PromptEngineer:
    """Assembles optimal prompts for each stage of ebook generation.

    The PromptEngineer combines:
    1. Base system prompts (genre-specific writer persona)
    2. Context modifiers (tone, style directives)
    3. Stage-specific templates (outline, chapter, frontmatter, etc.)
    4. Dynamic project context (book metadata, previous chapters, outline)
    """

    def __init__(self) -> None:
        self._custom_modifiers: list[str] = []

    def add_modifier(self, modifier_key: str) -> None:
        """Add a context modifier by key."""
        if modifier_key in CONTEXT_MODIFIERS:
            self._custom_modifiers.append(modifier_key)

    def remove_modifier(self, modifier_key: str) -> None:
        self._custom_modifiers = [m for m in self._custom_modifiers if m != modifier_key]

    def clear_modifiers(self) -> None:
        self._custom_modifiers.clear()

    # ------------------------------------------------------------------
    # System prompt construction
    # ------------------------------------------------------------------

    def build_system_prompt(
        self,
        ebook_type: EbookType,
        tone: str = "",
        extra_instructions: str = "",
    ) -> str:
        """Build the full system prompt for a given ebook type.

        Args:
            ebook_type: The genre of the book.
            tone: Optional tone override (formal, casual, dramatic, etc.).
            extra_instructions: Any additional instructions to append.

        Returns:
            The complete system prompt string.
        """
        base = BASE_SYSTEM_PROMPTS.get(
            ebook_type,
            BASE_SYSTEM_PROMPTS[EbookType.FICTION_NOVEL],
        )

        # Add tone modifier
        tone_map = {
            "formal": "tone_formal",
            "casual": "tone_casual",
            "dramatic": "tone_dramatic",
            "warm": "tone_warm",
            "technical": "tone_technical",
        }
        tone_key = tone_map.get(tone.lower() if tone else "")
        modifiers = list(self._custom_modifiers)
        if tone_key:
            modifiers.append(tone_key)

        # Add type-specific default modifiers
        if ebook_type in (EbookType.FICTION_NOVEL, EbookType.SCIFI_FANTASY,
                          EbookType.HISTORICAL_FICTION, EbookType.ROMANCE):
            if "show_dont_tell" not in modifiers:
                modifiers.append("show_dont_tell")
            if "sensory_rich" not in modifiers:
                modifiers.append("sensory_rich")
        elif ebook_type in (EbookType.NON_FICTION_GUIDE, EbookType.SELF_HELP,
                            EbookType.BUSINESS_BOOK, EbookType.TEXTBOOK):
            if "research_backed" not in modifiers:
                modifiers.append("research_backed")

        for mod_key in modifiers:
            base += CONTEXT_MODIFIERS.get(mod_key, "")

        if extra_instructions:
            base += f"\n\n{extra_instructions}"

        return base

    # ------------------------------------------------------------------
    # Outline prompt
    # ------------------------------------------------------------------

    def build_outline_prompt(
        self,
        project: BookProject,
        additional_instructions: str = "",
    ) -> tuple[str, str]:
        """Build the prompt for generating the book outline.

        Returns (system_prompt, user_prompt).
        """
        system = self.build_system_prompt(
            project.ebook_type,
            extra_instructions=(
                "You are now in OUTLINE MODE. Generate a structured outline only — "
                "do not write chapter content."
            ),
        )
        user = OUTLINE_PROMPT_TEMPLATE.format(
            title=project.metadata.title,
            ebook_type_label=EBOOK_TYPE_LABELS.get(project.ebook_type, "Book"),
            description=project.metadata.description or "No description provided.",
            target_audience=project.metadata.target_audience,
            total_chapters=project.generation_config.total_chapters,
            words_per_chapter=project.generation_config.words_per_chapter,
            additional_instructions=additional_instructions,
        )
        return system, user

    # ------------------------------------------------------------------
    # Chapter generation prompt
    # ------------------------------------------------------------------

    def build_chapter_prompt(
        self,
        project: BookProject,
        chapter: Chapter,
        previous_chapter_summary: str = "",
        outline_context: str = "",
        chapter_specific_instructions: str = "",
    ) -> tuple[str, str]:
        """Build the prompt for generating a single chapter.

        Returns (system_prompt, user_prompt).
        """
        system = self.build_system_prompt(project.ebook_type)
        user = CHAPTER_GENERATION_TEMPLATE.format(
            chapter_num=chapter.index + 1,
            book_title=project.metadata.title,
            author=project.metadata.author,
            system_context="",
            chapter_title=chapter.title,
            chapter_synopsis=chapter.synopsis or "Follow the outline.",
            previous_chapter_summary=(
                f"**Previous Chapter Summary:**\n{previous_chapter_summary}"
                if previous_chapter_summary else ""
            ),
            outline_context=(
                f"**Relevant Outline Section:**\n{outline_context}"
                if outline_context else ""
            ),
            target_words=project.generation_config.words_per_chapter,
            chapter_specific_instructions=chapter_specific_instructions,
        )
        return system, user

    # ------------------------------------------------------------------
    # Front/Back matter prompts
    # ------------------------------------------------------------------

    def build_frontmatter_prompt(self, project: BookProject) -> tuple[str, str]:
        system = self.build_system_prompt(
            project.ebook_type,
            extra_instructions="Generate professional front matter content only.",
        )
        dedication = (
            f"\nDedication: {project.metadata.dedication}"
            if project.metadata.dedication else ""
        )
        user = FRONTMATTER_PROMPT.format(
            title=project.metadata.title,
            author=project.metadata.author,
            ebook_type_label=EBOOK_TYPE_LABELS.get(project.ebook_type, "Book"),
            description=project.metadata.description or "No description provided.",
            dedication_section=dedication,
            custom_frontmatter="",
        )
        return system, user

    def build_backmatter_prompt(self, project: BookProject) -> tuple[str, str]:
        system = self.build_system_prompt(
            project.ebook_type,
            extra_instructions="Generate professional back matter content only.",
        )
        user = BACKMATTER_PROMPT.format(
            title=project.metadata.title,
            author=project.metadata.author,
            ebook_type_label=EBOOK_TYPE_LABELS.get(project.ebook_type, "Book"),
            description=project.metadata.description or "No description provided.",
            num_chapters=len(project.chapters),
            custom_backmatter="",
        )
        return system, user

    # ------------------------------------------------------------------
    # Chapter summary prompt (for context engineering)
    # ------------------------------------------------------------------

    def build_summary_prompt(
        self, chapter: Chapter, book_title: str = ""
    ) -> tuple[str, str]:
        system = (
            "You are a precise literary analyst. Summarize chapter content "
            "concisely, capturing only the most important plot points, "
            "character developments, and thematic elements."
        )
        user = CHAPTER_SUMMARY_TEMPLATE.format(
            chapter_title=chapter.title,
            chapter_content=chapter.content_markdown[:6000],
        )
        return system, user

    # ------------------------------------------------------------------
    # Custom chapter-specific instructions per type
    # ------------------------------------------------------------------

    def get_chapter_type_instructions(self, ebook_type: EbookType, chapter: Chapter) -> str:
        """Return type-specific instructions for a chapter being generated."""
        instructions = {
            EbookType.FICTION_NOVEL: (
                "Develop characters through action and dialogue. Include sensory "
                "details and subtext. Ensure the chapter advances the plot while "
                "deepening character relationships."
            ),
            EbookType.SHORT_STORIES: (
                "Make every word count. Create a complete narrative arc within this "
                "chapter. End with a resonant moment or image."
            ),
            EbookType.NON_FICTION_GUIDE: (
                "Present information clearly with headers, examples, and takeaways. "
                "Use analogies to explain complex ideas. Include practical tips "
                "the reader can apply immediately."
            ),
            EbookType.TECHNICAL_BOOK: (
                "Include working code examples with comments. Explain the 'why' "
                "behind each concept. Progress from simple to complex. Add "
                "common pitfalls and best practices."
            ),
            EbookType.SELF_HELP: (
                "Blend research, stories, and exercises. Give the reader concrete "
                "tools and frameworks. Be empathetic but direct. Include reflection "
                "questions or exercises."
            ),
            EbookType.COOKBOOK: (
                "Include 3-5 complete recipes with precise measurements, clear "
                "steps, prep/cook times, and serving sizes. Add chef's tips and "
                "variation suggestions."
            ),
            EbookType.CHILDREN_BOOK: (
                "Use simple, engaging language. Create vivid imagery. Include "
                "a gentle lesson or theme. Keep sentences relatively short and "
                "rhythmic."
            ),
            EbookType.POETRY_COLLECTION: (
                "Write 5-8 poems for this section. Vary form and length. Explore "
                "the collection's themes from different angles. Focus on imagery, "
                "sound, and emotional resonance."
            ),
            EbookType.TEXTBOOK: (
                "Begin with learning objectives. Present material with definitions, "
                "examples, and diagrams described in text. End with a summary and "
                "review questions."
            ),
            EbookType.MEMOIR_BIOGRAPHY: (
                "Recreate scenes with vivid detail and dialogue. Balance narrative "
                "with reflection. Connect personal experiences to universal themes."
            ),
            EbookType.BUSINESS_BOOK: (
                "Support arguments with data and case studies. Present actionable "
                "frameworks. Connect concepts to real business outcomes. Include "
                "key takeaways."
            ),
            EbookType.SCIFI_FANTASY: (
                "Reveal world-building details naturally through the narrative. "
                "Maintain consistency with established rules (magic/tech). Balance "
                "wonder with grounded character moments."
            ),
            EbookType.MYSTERY_THRILLER: (
                "Maintain and escalate tension. Plant clues naturally. Use red "
                "herrings sparingly. Control pacing — vary rhythm between fast "
                "and slow sections."
            ),
            EbookType.ROMANCE: (
                "Develop the romantic relationship naturally. Build chemistry "
                "through dialogue and small moments. Include internal monologue "
                "that reveals character depth."
            ),
            EbookType.HISTORICAL_FICTION: (
                "Ground the narrative in authentic historical detail. Weave real "
                "events naturally into the story. Use period-appropriate language "
                "without being inaccessible."
            ),
        }
        return instructions.get(ebook_type, "Write high-quality, engaging content.")