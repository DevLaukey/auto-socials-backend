"""
AI-powered comment generation service.

Generates contextual, platform-appropriate comments
for posts using configured AI provider.
"""

import json
import logging
import random
from typing import List, Dict, Optional, Tuple
from app.config import settings

logger = logging.getLogger(__name__)


class AICommentService:
    def __init__(self, platform: str = "general"):
        """
        Initialize AI comment service.
        
        Args:
            platform: 'youtube', 'instagram', 'twitter', or 'general'
        """
        self.platform = platform.lower()
        self.provider, self.client = self._get_provider()
        logger.info(f"AICommentService initialized for {platform} with provider {self.provider}")

    def _get_provider(self) -> Tuple[str, object]:
        """Get configured AI provider."""
        if getattr(settings, "OPENAI_API_KEY", None):
            from openai import OpenAI
            return "openai", OpenAI(api_key=settings.OPENAI_API_KEY)
        elif getattr(settings, "GROQ_API_KEY", None):
            from groq import Groq
            return "groq", Groq(api_key=settings.GROQ_API_KEY)
        else:
            logger.warning("No AI provider configured, using fallback responses")
            return "fallback", None

    def generate_comments(
        self,
        post_content: str,
        post_type: str,
        count: int = 1,
        style: str = "casual",
        context: Optional[Dict] = None,
        max_retries: int = 2
    ) -> List[str]:
        """
        Generate engaging comments for a post.
        
        Args:
            post_content: Title, caption, or description
            post_type: 'youtube', 'instagram', 'twitter'
            count: Number of comments to generate
            style: 'casual', 'funny', 'thoughtful', 'question', 'supportive'
            context: Additional context (hashtags, previous_comments, etc.)
            max_retries: Number of retries on failure
            
        Returns:
            List of generated comments
        """
        # Validate inputs
        if not post_content or not post_content.strip():
            logger.warning("Empty post content provided, using fallback comments")
            return self._get_fallback_comments(count, style)
        
        if count <= 0:
            return []
        
        # If no AI provider, use fallback
        if self.provider == "fallback" or not self.client:
            logger.info("Using fallback comment generation (no AI provider)")
            return self._get_fallback_comments(count, style)
        
        # Prepare prompts
        system_prompt = self._build_system_prompt(platform=self.platform, style=style)
        user_prompt = self._build_user_prompt(post_content, post_type, count, context)
        
        # Try generation with retries
        for attempt in range(max_retries + 1):
            try:
                if self.provider == "openai":
                    response = self.client.chat.completions.create(
                        model="gpt-4o-mini",
                        temperature=0.7 + (attempt * 0.1),  # Increase temperature on retry
                        max_tokens=500,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ]
                    )
                    raw_output = response.choices[0].message.content
                else:  # groq
                    response = self.client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        temperature=0.7 + (attempt * 0.1),
                        max_tokens=500,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ]
                    )
                    raw_output = response.choices[0].message.content
                
                # Parse output
                comments = self._parse_comments(raw_output)
                
                # Validate comments
                valid_comments = self._validate_comments(comments, post_type)
                
                if valid_comments:
                    # Return up to requested count
                    return valid_comments[:count]
                else:
                    logger.warning(f"No valid comments parsed from AI output (attempt {attempt + 1})")
                    
            except Exception as e:
                logger.error(f"Comment generation failed (attempt {attempt + 1}): {e}")
        
        # All retries failed, use fallback
        logger.warning("All comment generation attempts failed, using fallback")
        return self._get_fallback_comments(count, style)

    def generate_dm_reply(
        self,
        conversation_history: List[Dict],
        recipient_info: Dict,
        tone: str = "friendly",
        max_retries: int = 2
    ) -> str:
        """
        Generate an AI-powered DM reply.
        
        Args:
            conversation_history: List of previous messages with keys:
                - content: str
                - is_from_me: bool
                - created_at: Optional[datetime]
            recipient_info: Info about recipient (username, context)
            tone: Desired tone of reply
            max_retries: Number of retries on failure
            
        Returns:
            Generated message text
        """
        # If no AI provider, use fallback
        if self.provider == "fallback" or not self.client:
            return self._get_fallback_dm_reply(tone)
        
        # Build conversation history text
        history_text = ""
        for msg in conversation_history[-5:]:  # Last 5 messages
            sender = "You" if msg.get('is_from_me', False) else "Them"
            content = msg.get('content', '').strip()
            if content:
                history_text += f"{sender}: {content}\n"
        
        if not history_text:
            history_text = "No previous messages (new conversation)"
        
        system_prompt = self._build_dm_system_prompt(tone)
        
        user_prompt = f"""Conversation history:
{history_text}

Recipient: {recipient_info.get('username', 'Unknown')}
Context: {recipient_info.get('context', 'No additional context')}

Generate a natural, engaging reply that continues this conversation.
The reply should:
- Be 1-3 sentences maximum
- Match the tone: {tone}
- Encourage further engagement
- Not reveal you're an AI
- Be appropriate for the conversation context

Reply text only, no explanations or quotes."""
        
        for attempt in range(max_retries + 1):
            try:
                if self.provider == "openai":
                    response = self.client.chat.completions.create(
                        model="gpt-4o-mini",
                        temperature=0.8,
                        max_tokens=150,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ]
                    )
                    reply = response.choices[0].message.content.strip()
                else:  # groq
                    response = self.client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        temperature=0.8,
                        max_tokens=150,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ]
                    )
                    reply = response.choices[0].message.content.strip()
                
                # Clean up the reply
                reply = self._clean_dm_reply(reply)
                
                if reply and len(reply) > 5:
                    return reply
                    
            except Exception as e:
                logger.error(f"DM generation failed (attempt {attempt + 1}): {e}")
        
        return self._get_fallback_dm_reply(tone)

    def _build_system_prompt(self, platform: str, style: str) -> str:
        """Build system prompt for comment generation."""
        platform_guidelines = {
            "youtube": "- YouTube comments can be longer (1-3 sentences)\n- Be discussion-oriented\n- Can include thoughtful observations",
            "instagram": "- Instagram comments should be short (1-2 sentences)\n- Can use emojis occasionally\n- Be visually descriptive",
            "twitter": "- Twitter comments must be under 280 characters\n- Be concise and punchy\n- No hashtags unless relevant",
            "general": "- Keep comments natural and engaging\n- Match the platform's typical tone\n- Be authentic and human-like"
        }
        
        style_guidelines = {
            "casual": "- Friendly and conversational\n- Like a regular viewer/commenter",
            "funny": "- Humorous and witty\n- Not offensive or mean-spirited",
            "thoughtful": "- Insightful and adds value\n- Shows genuine engagement with content",
            "question": "- Ask engaging questions\n- Encourage discussion and replies",
            "supportive": "- Positive and encouraging\n- Supportive without being generic",
            "critical": "- Constructive criticism\n- Polite and respectful tone"
        }
        
        return f"""You are an expert social media engagement specialist.
Generate authentic, engaging comments for {platform} content.

PLATFORM GUIDELINES:
{platform_guidelines.get(platform, platform_guidelines["general"])}

STYLE GUIDELINES:
{style_guidelines.get(style, style_guidelines["casual"])}

RULES:
- Never use hashtags in comments unless they're part of the original post
- Avoid generic comments like "Nice post!" or "Great content!"
- Be specific to the content when possible
- Don't mention you're an AI or that you're generating comments
- Match the tone of similar comments on the platform
- Return ONLY a JSON array of strings, one per comment
- Each comment should be unique

EXAMPLES:
Good: ["This really resonates with me, especially the part about X!", "I've been looking for this exact information, thanks for sharing!"]
Bad: ["Nice post!", "Great content!", "Awesome!"]"""

    def _build_dm_system_prompt(self, tone: str) -> str:
        """Build system prompt for DM generation."""
        tone_guidelines = {
            "friendly": "- Warm and approachable\n- Use casual language\n- Show genuine interest",
            "professional": "- Polite and respectful\n- Clear and concise\n- Maintain professionalism",
            "casual": "- Relaxed and conversational\n- Like chatting with a friend\n- Can use occasional slang",
            "enthusiastic": "- Energetic and excited\n- Show enthusiasm\n- Use exclamation points occasionally",
            "helpful": "- Focus on providing value\n- Ask how you can assist\n- Be solution-oriented"
        }
        
        return f"""You are an AI assistant managing social media DMs for a business account.

TONE GUIDELINES:
{tone_guidelines.get(tone, tone_guidelines["friendly"])}

RULES:
- Keep responses natural and conversational
- Never reveal you're an AI
- Respond in a way that encourages engagement
- Be helpful and genuine
- Don't use emojis excessively (1-2 max if appropriate)
- Match the conversation's existing tone
- Keep replies concise (1-3 sentences)

IMPORTANT:
- Don't be overly salesy or promotional
- Listen to the conversation context
- Ask questions to keep conversation flowing
- Respect boundaries and don't be pushy"""

    def _build_user_prompt(self, post_content: str, post_type: str, count: int, context: Optional[Dict]) -> str:
        """Build user prompt for comment generation."""
        context_text = ""
        if context:
            if context.get('hashtags'):
                context_text += f"\nPost hashtags: {context['hashtags']}"
            if context.get('previous_comments'):
                # Limit to first 3 comments for context
                prev_comments = context['previous_comments'][:3]
                context_text += f"\nExisting comments on this post: {', '.join(prev_comments)}"
            if context.get('post_url'):
                context_text += f"\nPost URL: {context['post_url']}"
            if context.get('additional_info'):
                context_text += f"\nAdditional context: {context['additional_info']}"
        
        return f"""Generate {count} engaging comment(s) for this {post_type} post:

Post content: "{post_content}"{context_text}

Return ONLY a JSON array of strings. Example: ["Great point about X!", "I especially liked when you said Y"]"""

    def _parse_comments(self, raw_output: str) -> List[str]:
        """Parse AI output into list of comments."""
        if not raw_output:
            return []
        
        # Clean markdown code blocks
        raw_output = raw_output.strip()
        
        # Remove markdown code blocks
        if "```json" in raw_output:
            # Extract content between ```json and ```
            parts = raw_output.split("```json")
            if len(parts) > 1:
                raw_output = parts[1].split("```")[0].strip()
        elif "```" in raw_output:
            parts = raw_output.split("```")
            if len(parts) > 1:
                raw_output = parts[1].strip()
        
        # Try JSON parsing first
        try:
            comments = json.loads(raw_output)
            if isinstance(comments, list):
                # Clean each comment
                cleaned = []
                for c in comments:
                    if isinstance(c, str):
                        c = c.strip()
                        if c and not c.startswith(('"', "'")):  # Remove extra quotes
                            cleaned.append(c)
                return cleaned
        except json.JSONDecodeError:
            pass
        
        # Fallback: try to parse as line-separated list
        lines = []
        for line in raw_output.split('\n'):
            line = line.strip()
            # Remove bullet points, numbers, etc.
            line = line.lstrip('- ').lstrip('• ').lstrip('* ')
            # Remove leading numbers (e.g., "1. ")
            while line and line[0].isdigit() and len(line) > 2 and line[1] in ['.', ')']:
                line = line[2:].lstrip()
            
            if line and len(line) > 10:  # Minimum reasonable comment length
                lines.append(line)
        
        return lines

    def _validate_comments(self, comments: List[str], post_type: str) -> List[str]:
        """Validate and filter comments."""
        valid = []
        
        # Platform-specific max length
        max_length = {
            "twitter": 280,
            "instagram": 500,
            "youtube": 1000,
            "general": 1000
        }.get(post_type, 1000)
        
        for comment in comments:
            # Remove any extra quotes
            comment = comment.strip('"').strip("'").strip()
            
            # Check length
            if len(comment) > max_length:
                comment = comment[:max_length-3] + "..."
            
            # Check for generic comments to filter out
            generic_phrases = [
                "nice post", "great content", "awesome", "cool",
                "thanks for sharing", "good stuff", "love this",
                "amazing", "wonderful", "excellent", "fantastic"
            ]
            
            is_generic = any(
                phrase in comment.lower() and len(comment.split()) < 10
                for phrase in generic_phrases
            )
            
            if not is_generic and len(comment.split()) >= 3:
                valid.append(comment)
        
        return valid

    def _clean_dm_reply(self, reply: str) -> str:
        """Clean up a DM reply."""
        # Remove quotes if present
        reply = reply.strip('"').strip("'").strip()
        
        # Remove any "Reply:" or similar prefixes
        prefixes = ["Reply:", "Response:", "Message:", "DM:"]
        for prefix in prefixes:
            if reply.lower().startswith(prefix.lower()):
                reply = reply[len(prefix):].strip()
        
        return reply

    def _get_fallback_comments(self, count: int, style: str) -> List[str]:
        """Get fallback comments if AI fails."""
        fallbacks = {
            "casual": [
                "This is really well done! Thanks for sharing.",
                "I appreciate the effort you put into this.",
                "Really interesting perspective, hadn't thought of it that way."
            ],
            "question": [
                "How long did this take to create? Would love to know more about your process.",
                "What inspired this idea? It's really unique!",
                "Do you have any tips for someone just starting out with this?"
            ],
            "thoughtful": [
                "The attention to detail really shows here. Great work!",
                "This really makes you think about the topic differently.",
                "I like how you broke this down, makes it much easier to understand."
            ],
            "supportive": [
                "Keep up the great work! Really enjoying your content.",
                "This is exactly the kind of content I was looking for.",
                "So glad I found this, really helpful stuff!"
            ],
            "funny": [
                "Haha this is gold! 😂",
                "I can't be the only one who laughed at that!",
                "This made my day, thanks for the laugh!"
            ]
        }
        
        selected = fallbacks.get(style, fallbacks["casual"])
        
        # Return requested count, repeating if necessary
        if count <= len(selected):
            return selected[:count]
        else:
            # Repeat and possibly shuffle
            result = []
            while len(result) < count:
                result.extend(selected)
            return result[:count]

    def _get_fallback_dm_reply(self, tone: str) -> str:
        """Get fallback DM reply if AI fails."""
        fallbacks = {
            "friendly": "Thanks for reaching out! How can I help you today?",
            "professional": "Thank you for your message. I'll get back to you shortly.",
            "casual": "Hey! Thanks for the message. What's up?",
            "enthusiastic": "Thanks so much for reaching out! Really excited to connect!",
            "helpful": "Hi there! I'd be happy to help. What can I do for you?"
        }
        return fallbacks.get(tone, fallbacks["friendly"])