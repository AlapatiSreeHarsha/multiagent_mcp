import asyncio
import json
import os
import time
import base64
from pathlib import Path
from typing import List, Dict, Any
import google.generativeai as genai
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from PIL import ImageGrab
import pyautogui
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class LinkedInProjectAutomation:
    def __init__(self):
        # Load configuration from environment
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.project_folder_path = os.getenv("PROJECT_FOLDER_PATH")
        self.screenshot_count = int(os.getenv("SCREENSHOT_COUNT", 3))
        self.screenshot_delay = int(os.getenv("SCREENSHOT_DELAY", 2))
        self.max_caption_length = int(os.getenv("MAX_CAPTION_LENGTH", 3000))
        self.hashtag_count = int(os.getenv("HASHTAG_COUNT", 5))
        
        # MCP Server configuration
        self.server_url = "https://mcp.zapier.com/api/mcp/s/OWIzOGYwYjAtZTcwMy00YWU5LTllMTgtY2JiZWUxMzkyZjI4OjljNzcxNjMyLWQ5YzYtNDczZS04N2ExLWNlNjY3OTNhMmJhYw==/mcp"
        
        # Initialize Gemini
        genai.configure(api_key=self.google_api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Initialize MCP client
        self.transport = StreamableHttpTransport(self.server_url)
        self.client = Client(transport=self.transport)
        
        print("✅ LinkedIn Project Automation initialized")

    def read_project_files(self) -> Dict[str, str]:
        """Read all files from the project folder and return their contents"""
        project_data = {}
        project_path = Path(self.project_folder_path)
        
        if not project_path.exists():
            raise FileNotFoundError(f"Project folder not found: {self.project_folder_path}")
        
        # Supported file extensions
        supported_extensions = {'.py', '.js', '.html', '.css', '.md', '.txt', '.json', '.yaml', '.yml', '.xml', '.sql'}
        
        print(f"📁 Reading files from: {project_path}")
        
        for file_path in project_path.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                try:
                    relative_path = file_path.relative_to(project_path)
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        if content.strip():  # Only include non-empty files
                            project_data[str(relative_path)] = content
                            print(f"  ✅ Read: {relative_path}")
                except Exception as e:
                    print(f"  ❌ Error reading {file_path}: {e}")
        
        print(f"📊 Total files read: {len(project_data)}")
        return project_data

    def prepare_project_content(self, project_data: Dict[str, str]) -> str:
        """Prepare and structure project content for better analysis"""
        print("🔄 Preparing project content for analysis...")
        
        # Separate files by type for better organization
        categorized_files = {
            'main_files': [],
            'config_files': [],
            'documentation': [],
            'other_files': []
        }
        
        for file_path, content in project_data.items():
            file_lower = file_path.lower()
            if any(name in file_lower for name in ['main', 'app', 'index', '__init__']):
                categorized_files['main_files'].append((file_path, content))
            elif any(ext in file_lower for ext in ['.json', '.yaml', '.yml', '.env', 'config']):
                categorized_files['config_files'].append((file_path, content))
            elif any(ext in file_lower for ext in ['.md', '.txt', 'readme']):
                categorized_files['documentation'].append((file_path, content))
            else:
                categorized_files['other_files'].append((file_path, content))
        
        # Build structured content
        structured_content = "PROJECT ANALYSIS:\n\n"
        
        # Add project overview
        structured_content += "=== PROJECT OVERVIEW ===\n"
        structured_content += f"Total files: {len(project_data)}\n"
        structured_content += f"Main files: {len(categorized_files['main_files'])}\n"
        structured_content += f"Configuration files: {len(categorized_files['config_files'])}\n"
        structured_content += f"Documentation files: {len(categorized_files['documentation'])}\n"
        structured_content += f"Other files: {len(categorized_files['other_files'])}\n\n"
        
        # Add file contents in priority order
        for category, files in categorized_files.items():
            if files:
                structured_content += f"=== {category.upper().replace('_', ' ')} ===\n\n"
                for file_path, content in files:
                    # Limit individual file content to prevent overwhelming the AI
                    truncated_content = content[:5000] if len(content) > 5000 else content
                    if len(content) > 5000:
                        truncated_content += "\n... (content truncated due to length)"
                    
                    structured_content += f"--- FILE: {file_path} ---\n"
                    structured_content += f"{truncated_content}\n\n"
        
        # Overall content size management
        if len(structured_content) > 80000:  # Reduce from 100KB to 80KB for safety
            print("⚠️  Content too large, applying intelligent truncation...")
            # Keep the most important parts
            lines = structured_content.split('\n')
            important_lines = []
            current_length = 0
            
            for line in lines:
                if current_length + len(line) > 80000:
                    break
                important_lines.append(line)
                current_length += len(line) + 1
            
            structured_content = '\n'.join(important_lines)
            structured_content += "\n\n... (Additional content truncated for analysis efficiency)"
        
        print(f"📊 Structured content prepared: {len(structured_content)} characters")
        return structured_content

    async def generate_project_summary(self, project_data: Dict[str, str]) -> Dict[str, str]:
        """Generate project summary and LinkedIn post using Gemini with improved content preparation"""
        
        # Use improved content preparation
        project_content = self.prepare_project_content(project_data)
        
        # Enhanced prompt with better instructions
        prompt = f"""
        Analyze this software project and create a professional LinkedIn post about it.

        {project_content}

        Please provide:
        1. A comprehensive project summary (2-3 paragraphs)
        2. A compelling LinkedIn post with the following requirements:
           - Engaging title/hook
           - Clear description of what the project does
           - Technical highlights and key features
           - Professional tone suitable for LinkedIn
           - Include {self.hashtag_count} relevant hashtags
           - Maximum {self.max_caption_length} characters
           - Use emojis appropriately but sparingly
          

        Format your response as JSON:
        {{
            "project_summary": "detailed summary here",
            "linkedin_post": {{
                "title": "engaging title here",
                "caption": "full LinkedIn post content with hashtags"
            }}
        }}
        """
        
        print("🤖 Generating project summary with Gemini...")
        print(f"📊 Analyzing {len(project_data)} files...")
        
        try:
            # Generate content with explicit instructions
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,  # Lower temperature for more consistent, factual output
                    max_output_tokens=2048,
                )
            )
            
            # Extract and clean JSON from response
            response_text = response.text.strip()
            print(f"📝 Raw response length: {len(response_text)} characters")
            
            # Handle potential markdown formatting
            if '```json' in response_text:
                # Extract content between ```json and ```
                start = response_text.find('```json') + 7
                end = response_text.find('```', start)
                if end != -1:
                    response_text = response_text[start:end].strip()
            elif '```' in response_text:
                # Remove any ``` markers
                response_text = response_text.replace('```', '').strip()
            
            # Parse JSON
            result = json.loads(response_text)
            
            # Validate the result contains expected fields
            required_fields = ['project_summary', 'linkedin_post']
            missing_fields = [field for field in required_fields if field not in result]
            
            if missing_fields:
                raise ValueError(f"Missing required fields in AI response: {missing_fields}")
            
            # Validate LinkedIn post structure
            if 'title' not in result['linkedin_post'] or 'caption' not in result['linkedin_post']:
                raise ValueError("LinkedIn post missing title or caption")
            
            print("✅ Project summary generated successfully")
            print(f"📝 Title: {result['linkedin_post']['title']}")
            print(f"📊 Caption length: {len(result['linkedin_post']['caption'])} characters")
            
            # Show technical details if available
            if 'technical_details' in result:
                tech_details = result['technical_details']
                print(f"💻 Primary language: {tech_details.get('primary_language', 'N/A')}")
                print(f"🛠️  Frameworks: {', '.join(tech_details.get('frameworks_used', []))}")
                print(f"🎯 Project type: {tech_details.get('project_type', 'N/A')}")
            
            return result
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error: {e}")
            print(f"🔍 Response text preview: {response_text[:500]}...")
            return self._create_fallback_summary(project_data)
        except Exception as e:
            print(f"❌ Error generating summary: {e}")
            return self._create_fallback_summary(project_data)

    def _create_fallback_summary(self, project_data: Dict[str, str]) -> Dict[str, str]:
        """Create a basic fallback summary when AI generation fails"""
        print("🔄 Creating fallback summary based on file analysis...")
        
        # Analyze file types
        file_types = {}
        for file_path in project_data.keys():
            ext = Path(file_path).suffix.lower()
            file_types[ext] = file_types.get(ext, 0) + 1
        
        # Determine primary language
        language_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.html': 'HTML',
            '.css': 'CSS',
            '.java': 'Java',
            '.cpp': 'C++',
            '.c': 'C',
            '.php': 'PHP',
            '.rb': 'Ruby',
            '.go': 'Go'
        }
        
        primary_language = "Mixed"
        if file_types:
            most_common_ext = max(file_types.items(), key=lambda x: x[1])[0]
            primary_language = language_map.get(most_common_ext, most_common_ext.replace('.', '').upper())
        
        return {
            "project_summary": f"Software project containing {len(project_data)} files, primarily using {primary_language}. The project includes various components and demonstrates software development practices.",
            "linkedin_post": {
                "title": f"New {primary_language} Project Completed 🚀",
                "caption": f"Just completed a software project built with {primary_language}! 💻\n\nThis project includes {len(project_data)} files and showcases various development techniques. Excited to share the progress and continue building innovative solutions.\n\n#SoftwareDevelopment #{primary_language.replace(' ', '')} #Coding #Tech #Programming"
            }
        }

    def take_screenshots(self) -> List[str]:
        """Take screenshots automatically and return their paths"""
        screenshots = []
        screenshot_dir = Path("screenshots")
        screenshot_dir.mkdir(exist_ok=True)
        
        print(f"📸 Taking {self.screenshot_count} screenshots...")
        print("⚠️  Make sure your project is visible on screen!")
        
        # Give user time to prepare
        for i in range(5, 0, -1):
            print(f"Starting in {i}...")
            time.sleep(1)
        
        for i in range(self.screenshot_count):
            try:
                # Take screenshot
                screenshot = ImageGrab.grab()
                screenshot_path = screenshot_dir / f"screenshot_{i+1}_{int(time.time())}.png"
                screenshot.save(screenshot_path)
                screenshots.append(str(screenshot_path))
                
                print(f"  ✅ Screenshot {i+1} saved: {screenshot_path.name}")
                
                # Wait before next screenshot (except for the last one)
                if i < self.screenshot_count - 1:
                    time.sleep(self.screenshot_delay)
                    
            except Exception as e:
                print(f"  ❌ Error taking screenshot {i+1}: {e}")
        
        print(f"📸 Completed: {len(screenshots)} screenshots taken")
        return screenshots

    def encode_image_to_base64(self, image_path: str) -> str:
        """Convert image to base64 for API upload"""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            print(f"❌ Error encoding image {image_path}: {e}")
            return ""

    async def post_to_linkedin(self, post_data: Dict[str, str], screenshot_paths: List[str]):
        """Post content to LinkedIn using MCP - Personal Share Only"""
        print("🔗 Connecting to LinkedIn via MCP...")
        
        try:
            async with self.client:
                print(f"✅ MCP Client connected: {self.client.is_connected()}")
                
                # Get available tools
                tools = await self.client.list_tools()
                available_tools = [t.name for t in tools]
                print(f"🛠️  Available tools: {available_tools}")
                
                # Prepare the post content
                title = post_data['linkedin_post']['title']
                caption = post_data['linkedin_post']['caption']
                
                # Only use personal share update
                if "linkedin_create_share_update" in available_tools:
                    print("👤 Posting as personal share...")
                    
                    result = await self.client.call_tool(
                        "linkedin_create_share_update",
                        {
                            "instructions": "Create a LinkedIn personal share post",
                            "comment": f"{title}\n\n{caption}",
                            "content__title": title,
                            "visibility__code": "anyone",  # or "connections"
                        },
                    )
                    
                    # Parse and display result
                    if result and len(result) > 0:
                        json_result = json.loads(result[0].text)
                        print(f"✅ LinkedIn personal post created successfully!")
                        print(f"📋 Result: {json.dumps(json_result, indent=2)}")
                        return True
                    else:
                        print("❌ No result returned from LinkedIn API")
                        return False
                        
                else:
                    print("❌ linkedin_create_share_update tool not found")
                    print(f"Available tools: {available_tools}")
                    return False
                    
        except Exception as e:
            print(f"❌ Error posting to LinkedIn: {e}")
            return False

    async def run_automation(self):
        """Main automation workflow"""
        try:
            print("🚀 Starting LinkedIn Project Automation...\n")
            
            # Step 1: Read project files
            print("=" * 50)
            print("STEP 1: Reading Project Files")
            print("=" * 50)
            project_data = self.read_project_files()
            
            if not project_data:
                print("❌ No files found to analyze!")
                return
            
            # Step 2: Generate summary and post content
            print("\n" + "=" * 50)
            print("STEP 2: Generating Content with Gemini")
            print("=" * 50)
            summary_data = await self.generate_project_summary(project_data)
            
            # Step 3: Take screenshots
            print("\n" + "=" * 50)
            print("STEP 3: Taking Screenshots")
            print("=" * 50)
            screenshots = self.take_screenshots()
            
            # Step 4: Post to LinkedIn (Personal Share Only)
            print("\n" + "=" * 50)
            print("STEP 4: Posting to LinkedIn (Personal Share)")
            print("=" * 50)
            success = await self.post_to_linkedin(summary_data, screenshots)
            
            # Summary
            print("\n" + "=" * 50)
            print("AUTOMATION COMPLETED")
            print("=" * 50)
            print(f"📁 Files analyzed: {len(project_data)}")
            print(f"📸 Screenshots taken: {len(screenshots)}")
            print(f"🔗 LinkedIn personal post: {'✅ Success' if success else '❌ Failed'}")
            
            if success:
                print("\n🎉 Your project has been successfully posted to LinkedIn as a personal share!")
            else:
                print("\n⚠️  Post content generated but LinkedIn posting failed.")
                print("📝 Generated content:")
                print(f"Title: {summary_data['linkedin_post']['title']}")
                print(f"Caption: {summary_data['linkedin_post']['caption']}")
            
        except Exception as e:
            print(f"❌ Automation failed: {e}")

# Main execution
async def main():
    automation = LinkedInProjectAutomation()
    await automation.run_automation()

if __name__ == "__main__":
    asyncio.run(main())