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
import requests

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
        self.drive_folder_name = os.getenv("DRIVE_FOLDER_NAME", "LinkedIn Screenshots")
        
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

    async def generate_project_summary(self, project_data: Dict[str, str], drive_links: List[str] = None) -> Dict[str, str]:
        """Generate project summary and LinkedIn post using Gemini"""
        
        # Prepare project content for analysis
        project_content = "PROJECT FILES ANALYSIS:\n\n"
        for file_path, content in project_data.items():
            project_content += f"=== FILE: {file_path} ===\n{content}\n\n"
        
        # Limit content size for API
        if len(project_content) > 100000:  # ~100KB limit
            project_content = project_content[:100000] + "\n... (content truncated)"
        
        # Add screenshot information if available
        screenshot_info = ""
        if drive_links:
            screenshot_info = f"\n\nSCREENSHOT LINKS:\nThe following Google Drive links contain screenshots of the project:\n"
            for i, link in enumerate(drive_links, 1):
                screenshot_info += f"{i}. {link}\n"
            screenshot_info += "\nMention these links in the LinkedIn post so people can view the screenshots."

        prompt = f"""
        Analyze this software project and create a professional LinkedIn post about it.

        {project_content}{screenshot_info}

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
           {"- Include the Google Drive screenshot links in the post for people to view" if drive_links else "- Mention that the project includes visual elements"}

        Format your response as JSON:
        {{
            "project_summary": "detailed summary here",
            "linkedin_post": {{
                "title": "engaging title here",
                "caption": "full LinkedIn post content with hashtags{' and screenshot links' if drive_links else ''}"
            }}
        }}
        """
        
        print("🤖 Generating project summary with Gemini...")
        
        try:
            response = self.model.generate_content(prompt)
            
            # Extract JSON from response
            response_text = response.text.strip()
            
            # Handle potential markdown formatting
            if response_text.startswith('```json'):
                response_text = response_text.replace('```json', '').replace('```', '').strip()
            elif response_text.startswith('```'):
                response_text = response_text.replace('```', '').strip()
            
            result = json.loads(response_text)
            
            print("✅ Project summary generated successfully")
            print(f"📝 Title: {result['linkedin_post']['title']}")
            print(f"📊 Caption length: {len(result['linkedin_post']['caption'])} characters")
            
            return result
            
        except Exception as e:
            print(f"❌ Error generating summary: {e}")
            # Fallback summary
            fallback_caption = f"Just completed an exciting software project! 🚀"
            if drive_links:
                fallback_caption += f"\n\nCheck out the screenshots here:\n" + "\n".join(drive_links)
            fallback_caption += f"\n\n#SoftwareDevelopment #Coding #Tech #Programming #Developer"
            
            return {
                "project_summary": "Software project analysis completed",
                "linkedin_post": {
                    "title": "New Software Project Completed 🚀",
                    "caption": fallback_caption
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

    async def create_drive_folder(self) -> str:
        """Create or find the Google Drive folder for screenshots"""
        print(f"📁 Creating/finding Google Drive folder: {self.drive_folder_name}")
        
        try:
            # First, try to find existing folder
            result = await self.client.call_tool(
                "google_drive_find_a_folder",
                {
                    "instructions": f"Find a folder named '{self.drive_folder_name}' in Google Drive",
                    "title": self.drive_folder_name
                }
            )
            
            if result and len(result) > 0:
                print(f"🔍 Find folder result: {result[0].text}")
                folder_data = json.loads(result[0].text)
                if folder_data and 'files' in folder_data and len(folder_data['files']) > 0:
                    folder_id = folder_data['files'][0]['id']
                    print(f"✅ Found existing folder: {folder_id}")
                    return folder_id
            
            # If folder doesn't exist, create it
            print("📁 Creating new folder...")
            result = await self.client.call_tool(
                "google_drive_create_folder",
                {
                    "instructions": f"Create a new folder named '{self.drive_folder_name}' in Google Drive",
                    "title": self.drive_folder_name
                }
            )
            
            if result and len(result) > 0:
                print(f"📁 Create folder result: {result[0].text}")
                folder_data = json.loads(result[0].text)
                print(f"📁 Parsed folder data: {folder_data}")
                
                # Try different possible keys for folder ID
                folder_id = folder_data.get('id') or folder_data.get('file_id') or folder_data.get('folder_id')
                
                if folder_id:
                    print(f"✅ Created new folder: {folder_id}")
                    return folder_id
                else:
                    print(f"⚠️ Folder created but no ID found in response")
            
        except Exception as e:
            print(f"❌ Error with Drive folder: {e}")
        
        return None

    async def upload_screenshots_to_drive(self, screenshot_paths: List[str]) -> List[str]:
        """Upload screenshots to Google Drive and return shareable links"""
        print("☁️ Uploading screenshots to Google Drive...")
        drive_links = []
        
        try:
            async with self.client:
                # Create/find the folder first
                folder_id = await self.create_drive_folder()
                
                for i, screenshot_path in enumerate(screenshot_paths):
                    try:
                        print(f"📤 Uploading screenshot {i+1}/{len(screenshot_paths)}: {Path(screenshot_path).name}")
                        
                        # Method 1: Try google_drive_create_file_from_text with base64
                        try:
                            with open(screenshot_path, 'rb') as img_file:
                                img_data = base64.b64encode(img_file.read()).decode('utf-8')
                            
                            # Try creating file from text/data
                            upload_params = {
                                "instructions": f"Upload screenshot image file '{Path(screenshot_path).name}' to Google Drive as PNG image",
                                "title": f"screenshot_{i+1}_{int(time.time())}.png",
                                "file": f"data:image/png;base64,{img_data}"
                            }
                            
                            if folder_id:
                                upload_params["folder"] = folder_id
                            
                            result = await self.client.call_tool(
                                "google_drive_create_file_from_text",
                                upload_params
                            )
                            
                            if result and len(result) > 0:
                                print(f"📤 Upload result: {result[0].text}")
                                upload_data = json.loads(result[0].text)
                                print(f"📤 Parsed upload data: {upload_data}")
                                
                                # Try different possible keys for file ID
                                file_id = upload_data.get('id') or upload_data.get('file_id') or upload_data.get('fileId')
                                
                                if file_id:
                                    print(f"  ✅ Uploaded successfully, ID: {file_id}")
                                    
                                    # Create shareable link
                                    drive_link = await self.create_shareable_link(file_id, i+1)
                                    if drive_link:
                                        drive_links.append(drive_link)
                                    
                                    continue  # Successfully uploaded, move to next file
                            
                        except Exception as e:
                            print(f"  ⚠️ Method 1 failed: {e}")
                        
                        # Method 2: Try the original google_drive_upload_file method
                        try:
                            with open(screenshot_path, 'rb') as img_file:
                                img_data = base64.b64encode(img_file.read()).decode('utf-8')
                            
                            upload_params = {
                                "instructions": f"Upload screenshot image file '{Path(screenshot_path).name}' to Google Drive",
                                "file": img_data,
                                "title": f"screenshot_{i+1}_{int(time.time())}.png"
                            }
                            
                            if folder_id:
                                upload_params["folder"] = folder_id
                            
                            result = await self.client.call_tool(
                                "google_drive_upload_file",
                                upload_params
                            )
                            
                            if result and len(result) > 0:
                                print(f"📤 Upload result (method 2): {result[0].text}")
                                upload_data = json.loads(result[0].text)
                                print(f"📤 Parsed upload data (method 2): {upload_data}")
                                
                                # Try different possible keys for file ID
                                file_id = upload_data.get('id') or upload_data.get('file_id') or upload_data.get('fileId')
                                
                                if file_id:
                                    print(f"  ✅ Uploaded successfully (method 2), ID: {file_id}")
                                    
                                    # Create shareable link
                                    drive_link = await self.create_shareable_link(file_id, i+1)
                                    if drive_link:
                                        drive_links.append(drive_link)
                                    
                                    continue  # Successfully uploaded, move to next file
                            
                        except Exception as e:
                            print(f"  ⚠️ Method 2 failed: {e}")
                        
                        # Method 3: Save file locally and reference by path
                        try:
                            # Try using file path instead of base64
                            upload_params = {
                                "instructions": f"Upload the screenshot file at path '{screenshot_path}' to Google Drive",
                                "file": screenshot_path,
                                "title": f"screenshot_{i+1}_{int(time.time())}.png"
                            }
                            
                            if folder_id:
                                upload_params["folder"] = folder_id
                            
                            result = await self.client.call_tool(
                                "google_drive_upload_file",
                                upload_params
                            )
                            
                            if result and len(result) > 0:
                                print(f"📤 Upload result (method 3): {result[0].text}")
                                upload_data = json.loads(result[0].text)
                                
                                file_id = upload_data.get('id') or upload_data.get('file_id') or upload_data.get('fileId')
                                
                                if file_id:
                                    print(f"  ✅ Uploaded successfully (method 3), ID: {file_id}")
                                    
                                    # Create shareable link
                                    drive_link = await self.create_shareable_link(file_id, i+1)
                                    if drive_link:
                                        drive_links.append(drive_link)
                                    
                                    continue
                            
                        except Exception as e:
                            print(f"  ⚠️ Method 3 failed: {e}")
                        
                        print(f"  ❌ All upload methods failed for screenshot {i+1}")
                            
                    except Exception as e:
                        print(f"  ❌ Error uploading screenshot {i+1}: {e}")
                
        except Exception as e:
            print(f"❌ Error during Drive upload process: {e}")
        
        print(f"☁️ Drive upload completed: {len(drive_links)} screenshots uploaded successfully")
        return drive_links

    async def create_shareable_link(self, file_id: str, screenshot_num: int) -> str:
        """Create a shareable link for the uploaded file"""
        try:
            # Make the file publicly viewable
            share_result = await self.client.call_tool(
                "google_drive_add_file_sharing_preference",
                {
                    "instructions": f"Make the uploaded screenshot file publicly viewable with read access",
                    "file_id": file_id,
                    "role": "reader",
                    "type": "anyone"
                }
            )
            
            if share_result and len(share_result) > 0:
                print(f"📤 Share result: {share_result[0].text}")
                share_data = json.loads(share_result[0].text)
                
                # Try different possible keys for the link
                link = (share_data.get('webViewLink') or 
                       share_data.get('alternateLink') or 
                       share_data.get('link') or
                       share_data.get('url'))
                
                if link:
                    print(f"  ✅ Made public: {link}")
                    return link
                else:
                    # Fallback to standard Drive link
                    standard_link = f"https://drive.google.com/file/d/{file_id}/view"
                    print(f"  ✅ Standard link: {standard_link}")
                    return standard_link
            else:
                # Fallback to standard Drive link
                standard_link = f"https://drive.google.com/file/d/{file_id}/view"
                print(f"  ✅ Standard link: {standard_link}")
                return standard_link
                
        except Exception as e:
            print(f"  ⚠️ Error making file public: {e}")
            # Still return the standard link
            standard_link = f"https://drive.google.com/file/d/{file_id}/view"
            print(f"  ✅ Standard link: {standard_link}")
            return standard_link

    async def post_to_linkedin(self, post_data: Dict[str, str], drive_links: List[str]):
        """Post content to LinkedIn with Google Drive links"""
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
                full_content = f"{title}\n\n{caption}"
                
                # Add drive links if not already included in caption
                if drive_links and not any(link in caption for link in drive_links):
                    full_content += f"\n\n📸 Project Screenshots:\n" + "\n".join(drive_links)
                
                success = False
                
                # Try to post using linkedin_create_share_update
                if "linkedin_create_share_update" in available_tools:
                    print("📝 Creating LinkedIn post...")
                    try:
                        result = await self.client.call_tool(
                            "linkedin_create_share_update",
                            {
                                "instructions": "Create a professional LinkedIn post sharing my project with the provided content",
                                "comment": full_content,
                                "content__title": title,
                                "visibility__code": "anyone"
                            }
                        )
                        
                        if result and len(result) > 0:
                            json_result = json.loads(result[0].text)
                            print(f"✅ LinkedIn post created successfully!")
                            print(f"📋 Result: {json.dumps(json_result, indent=2)}")
                            success = True
                    except Exception as e:
                        print(f"❌ Error creating LinkedIn post: {e}")
                
                # If automated posting fails, provide manual posting option
                if not success:
                    print("⚠️  Automated posting failed. Providing manual posting information...")
                    print("\n📋 MANUAL POSTING CONTENT:")
                    print("=" * 50)
                    print(f"TITLE: {title}")
                    print(f"\nFULL CONTENT:\n{full_content}")
                    if drive_links:
                        print(f"\nSCREENSHOT LINKS:")
                        for i, link in enumerate(drive_links, 1):
                            print(f"  {i}. {link}")
                    print("=" * 50)
                    print("💡 Please copy the content above and post manually to LinkedIn")
                    
                    # Save content to file for easy copying
                    manual_post_file = Path("manual_linkedin_post.txt")
                    with open(manual_post_file, 'w', encoding='utf-8') as f:
                        f.write(f"LINKEDIN POST CONTENT\n")
                        f.write(f"{'='*50}\n")
                        f.write(f"TITLE: {title}\n\n")
                        f.write(f"FULL CONTENT:\n{full_content}\n\n")
                        if drive_links:
                            f.write(f"SCREENSHOT LINKS:\n")
                            for i, link in enumerate(drive_links, 1):
                                f.write(f"  {i}. {link}\n")
                    
                    print(f"💾 Content saved to: {manual_post_file}")
                    return False
                
                return success
                    
        except Exception as e:
            print(f"❌ Error posting to LinkedIn: {e}")
            return False

    async def run_automation(self):
        """Main automation workflow"""
        try:
            print("🚀 Starting LinkedIn Project Automation with Google Drive Integration...\n")
            
            # Step 1: Read project files
            print("=" * 50)
            print("STEP 1: Reading Project Files")
            print("=" * 50)
            project_data = self.read_project_files()
            
            if not project_data:
                print("❌ No files found to analyze!")
                return
            
            # Step 2: Take screenshots
            print("\n" + "=" * 50)
            print("STEP 2: Taking Screenshots")
            print("=" * 50)
            screenshots = self.take_screenshots()
            
            # Step 3: Upload screenshots to Google Drive
            drive_links = []
            if screenshots:
                print("\n" + "=" * 50)
                print("STEP 3: Uploading Screenshots to Google Drive")
                print("=" * 50)
                drive_links = await self.upload_screenshots_to_drive(screenshots)
            
            # Step 4: Generate summary and post content (including drive links)
            print("\n" + "=" * 50)
            print("STEP 4: Generating Content with Gemini")
            print("=" * 50)
            summary_data = await self.generate_project_summary(project_data, drive_links)
            
            # Step 5: Post to LinkedIn with Google Drive links
            print("\n" + "=" * 50)
            print("STEP 5: Posting to LinkedIn with Google Drive Links")
            print("=" * 50)
            success = await self.post_to_linkedin(summary_data, drive_links)
            
            # Summary
            print("\n" + "=" * 50)
            print("AUTOMATION COMPLETED")
            print("=" * 50)
            print(f"📁 Files analyzed: {len(project_data)}")
            print(f"📸 Screenshots taken: {len(screenshots)}")
            print(f"☁️ Screenshots uploaded to Drive: {len(drive_links)}")
            print(f"🔗 LinkedIn post: {'✅ Success' if success else '❌ Failed/Manual'}")
            
            if success:
                print("\n🎉 Your project has been successfully posted to LinkedIn with Google Drive screenshot links!")
            else:
                print("\n⚠️  Automated posting failed, but all content and screenshots are ready for manual posting.")
                print("📝 Check the generated files for manual posting instructions.")
                
            if drive_links:
                print(f"\n📸 Your screenshots are available at:")
                for i, link in enumerate(drive_links, 1):
                    print(f"  {i}. {link}")
            
        except Exception as e:
            print(f"❌ Automation failed: {e}")

# Main execution
async def main():
    automation = LinkedInProjectAutomation()
    await automation.run_automation()

if __name__ == "__main__":
    asyncio.run(main())