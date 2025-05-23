#!/usr/bin/env python3
"""
GitAgent: A simplified tool that analyzes local files, generates README.md, and pushes to GitHub.
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path
import git
import google.generativeai as genai
from dotenv import load_dotenv
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GitAgent:
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Get environment variables
        self.github_username = os.getenv("GITHUB_USERNAME")
        self.github_email = os.getenv("GITHUB_EMAIL")
        self.github_repo_url = os.getenv("GITHUB_REPO_URL")
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.user_files_path = os.getenv("USER_FILES_PATH")
        
        # Validate environment variables
        self._validate_env_vars()
        
        # Initialize paths
        self.user_files_path = Path(self.user_files_path)
        self.temp_dir = None
        
        # Configure Google Gemini API
        genai.configure(api_key=self.api_key)
        
        # Initialize the model directly
        self.model = genai.GenerativeModel('gemini-2.0-flash')
    
    def _validate_env_vars(self):
        """Validate that all required environment variables are set."""
        required_vars = {
            "GITHUB_USERNAME": self.github_username,
            "GITHUB_EMAIL": self.github_email,
            "GEMINI_API_KEY": self.api_key,
            "GITHUB_REPO_URL": self.github_repo_url,
            "USER_FILES_PATH": self.user_files_path
        }
        
        missing_vars = [key for key, value in required_vars.items() if not value]
        
        if missing_vars:
            logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
            logger.error("Please check your .env file.")
            sys.exit(1)
            
        # Additional validation
        if not os.path.exists(self.user_files_path):
            logger.error(f"User files path does not exist: {self.user_files_path}")
            sys.exit(1)
    
    def analyze_files(self):
        """Analyzes files in the specified directory."""
        logger.info(f"Analyzing files in: {self.user_files_path}")
        
        file_data = []
        ignored_dirs = ['.git', '__pycache__', 'node_modules', '.vscode', '.idea']
        ignored_extensions = ['.pyc', '.pyo', '.pyd', '.git', '.DS_Store']
        
        for root, dirs, files in os.walk(self.user_files_path):
            # Skip ignored directories
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            
            for file in files:
                # Skip ignored file extensions
                if any(file.endswith(ext) for ext in ignored_extensions):
                    continue
                
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, self.user_files_path)
                
                try:
                    # Only read text files and limit size to avoid memory issues
                    if os.path.getsize(file_path) < 1_000_000:  # 1MB limit
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read(10000)  # Read first 10000 chars
                                if len(content) >= 10000:
                                    content = content + "\n... [content truncated]"
                                    
                            file_data.append({
                                "path": relative_path,
                                "content": content
                            })
                        except UnicodeDecodeError:
                            file_data.append({
                                "path": relative_path,
                                "content": "[binary file]"
                            })
                    else:
                        file_data.append({
                            "path": relative_path,
                            "content": "[file too large]"
                        })
                        
                except Exception as e:
                    logger.warning(f"Error reading file {file_path}: {e}")
        
        logger.info(f"Found {len(file_data)} files")
        return file_data
    
    def generate_readme(self, file_data):
        """Generates a README.md file based on file analysis."""
        logger.info("Generating README.md file")
        
        # Create temp directory for preparation
        self.temp_dir = tempfile.mkdtemp()
        logger.info(f"Created temporary directory: {self.temp_dir}")
        
        # Get directory structure
        directory_structure = self._get_directory_structure(self.user_files_path)
        
        # Prepare file contents for the prompt
        files_summary = []
        for file_info in file_data:
            files_summary.append(f"--- {file_info['path']} ---\n{file_info['content']}\n")
        
        # Generate README content using Gemini
        prompt = f"""
        Create a comprehensive README.md file for a project with the following files and their contents:

        Files and their contents:
        {chr(10).join(files_summary)}

        Directory structure:
        {directory_structure}

        Based on the actual file contents above, create a README.md that:
        1. Accurately describes what the project does based on the actual code
        2. Lists the actual features implemented in the code
        3. Includes installation instructions if there are dependencies
        4. Provides accurate usage instructions based on the actual code
        5. Shows the actual file structure
        6. Includes any necessary setup or configuration steps

        The README should be specific to this project and not use placeholder text.
        Format it in proper Markdown with appropriate headers, code blocks, and formatting.
        """
        
        try:
            response = self.model.generate_content(prompt)
            readme_content = response.text
            
            # Write README to temp directory
            readme_path = os.path.join(self.temp_dir, "README.md")
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(readme_content)
            
            logger.info(f"README.md generated and saved to {readme_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error generating README: {e}")
            return False
    
    def _get_directory_structure(self, path, prefix='', max_depth=3, current_depth=0):
        """Helper function to get a text representation of the directory structure."""
        if current_depth > max_depth:
            return []
            
        result = []
        path = Path(path)
        
        items = []
        try:
            items = sorted(path.iterdir())
        except PermissionError:
            return [f"{prefix}└── [Permission Denied]"]
        
        for item in items:
            if item.name.startswith('.'):
                continue
                
            if item.is_dir():
                result.append(f"{prefix}├── {item.name}/")
                sub_items = self._get_directory_structure(item, prefix + "│   ", max_depth, current_depth + 1)
                result.extend(sub_items)
            else:
                result.append(f"{prefix}├── {item.name}")
                
        return result
    
    def push_to_github(self):
        """Copies user files to temp dir, adds README.md, and pushes to GitHub."""
        if not self.temp_dir:
            logger.error("README must be generated first")
            return False
        
        logger.info(f"Pushing to GitHub repository: {self.github_repo_url}")
        
        try:
            # Copy all files from user directory to temp directory
            logger.info("Copying user files to temporary directory...")
            copied_files = []
            for item in os.listdir(self.user_files_path):
                src_path = os.path.join(self.user_files_path, item)
                dst_path = os.path.join(self.temp_dir, item)
                
                if os.path.isfile(src_path):
                    shutil.copy2(src_path, dst_path)
                    copied_files.append(item)
                    logger.info(f"Copied file: {item}")
                elif os.path.isdir(src_path) and not item.startswith('.'):
                    shutil.copytree(src_path, dst_path, ignore=shutil.ignore_patterns('*.pyc', '__pycache__'))
                    copied_files.append(f"{item}/")
                    logger.info(f"Copied directory: {item}")
            
            logger.info(f"Total copied items: {copied_files}")
            
            # Verify README.md exists
            readme_path = os.path.join(self.temp_dir, "README.md")
            if os.path.exists(readme_path):
                logger.info(f"README.md exists in temp dir, size: {os.path.getsize(readme_path)} bytes")
            else:
                logger.error("README.md not found in temp directory!")
                return False
            
            # Initialize git repo in temp directory
            logger.info("Initializing Git repository...")
            repo = git.Repo.init(self.temp_dir)
            
            # Configure git
            with repo.config_writer() as git_config:
                git_config.set_value('user', 'name', self.github_username)
                git_config.set_value('user', 'email', self.github_email)
                # Disable GPG signing for this repository
                git_config.set_value('commit', 'gpgsign', 'false')
            
            # Add all files in the temp directory
            logger.info("Adding files to Git...")
            repo.git.add('.')
            
            # List all files in the temp directory for debugging
            all_files = []
            for root, dirs, files in os.walk(self.temp_dir):
                for file in files:
                    rel_path = os.path.relpath(os.path.join(root, file), self.temp_dir)
                    all_files.append(rel_path)
            
            logger.info(f"Files in temp directory: {all_files}")
            logger.info(f"Git untracked files: {repo.untracked_files}")
            
            # Check if there are files to commit
            if not all_files:
                logger.error("No files found in temp directory")
                return False
            
            if not repo.untracked_files:
                logger.warning("Git shows no untracked files, but files exist. This might be a Git issue.")
                # Force add all files
                repo.git.add('--all')
                logger.info("Force added all files")
            
            # Commit changes - always try to commit if files exist
            logger.info("Attempting to commit files...")
            try:
                # Check if there's anything staged
                staged_files = repo.index.diff("HEAD") if repo.head.is_valid() else list(repo.index.entries.keys())
                logger.info(f"Staged files: {len(staged_files) if isinstance(staged_files, list) else 'checking...'}")
                
                # Try to commit (disable GPG signing)
                commit_result = repo.git.commit('-m', 'Initial commit with generated README.md', '--no-gpg-sign')
                logger.info(f"Commit successful: {commit_result}")
            except git.GitCommandError as e:
                error_msg = str(e).lower()
                if "nothing to commit" in error_msg:
                    logger.error("Git says nothing to commit even though files exist")
                    logger.error("This might be due to:")
                    logger.error("1. All files are ignored by .gitignore")
                    logger.error("2. Files are binary and Git is having issues")
                    logger.error("3. File permissions issue")
                    return False
                else:
                    logger.error(f"Commit failed: {e}")
                    return False
            
            # Add remote origin
            logger.info("Setting up remote repository...")
            try:
                # Remove existing remote if it exists
                try:
                    repo.delete_remote('origin')
                    logger.debug("Removed existing origin remote")
                except:
                    pass  # Remote doesn't exist, which is fine
                
                origin = repo.create_remote('origin', self.github_repo_url)
                logger.info(f"Added remote origin: {self.github_repo_url}")
            except Exception as e:
                logger.error(f"Failed to add remote: {e}")
                return False
            
            # Push to GitHub
            logger.info("Pushing to GitHub...")
            try:
                # Ensure we're on the main branch
                try:
                    repo.git.checkout('-b', 'main')
                    logger.debug("Created and switched to main branch")
                except git.GitCommandError:
                    # Branch might already exist or we're already on it
                    try:
                        repo.git.checkout('main')
                        logger.debug("Switched to existing main branch")
                    except git.GitCommandError:
                        logger.debug("Using current branch")
                
                # Push with upstream setting
                push_result = origin.push('main', set_upstream=True, force=True)
                
                # Check push result
                for push_info in push_result:
                    if push_info.flags & push_info.ERROR:
                        logger.error(f"Push error: {push_info.summary}")
                        return False
                    elif push_info.flags & push_info.UP_TO_DATE:
                        logger.info("Repository is already up to date")
                    else:
                        logger.info(f"Push successful: {push_info.summary}")
                
                logger.info("Successfully pushed to GitHub repository")
                return True
                
            except git.GitCommandError as e:
                error_msg = str(e)
                logger.error(f"Push failed: {error_msg}")
                
                if "Authentication failed" in error_msg or "fatal: Authentication failed" in error_msg:
                    logger.error("GitHub authentication failed. Please check your credentials.")
                    print("\n🔑 Authentication failed. Make sure you have:")
                    print("   - Set up SSH keys for GitHub, OR")
                    print("   - Use a personal access token in the repository URL")
                    print("   - Example with token: https://your_token@github.com/username/repo.git")
                elif "Permission denied" in error_msg:
                    logger.error("Permission denied. Please check your repository access rights.")
                elif "Repository not found" in error_msg:
                    logger.error("Repository not found. Please check your repository URL.")
                elif "remote: Repository not found" in error_msg:
                    logger.error("Repository not found on GitHub. Please create the repository first.")
                    print(f"\n📁 Please create the repository at: {self.github_repo_url}")
                
                return False
            
        except Exception as e:
            logger.error(f"Error during GitHub push: {str(e)}")
            return False
        finally:
            # Clean up: Remove temporary directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    # On Windows, we need to handle file permissions
                    def handle_remove_readonly(func, path, exc):
                        import stat
                        os.chmod(path, stat.S_IWRITE)
                        func(path)
                    
                    shutil.rmtree(self.temp_dir, onerror=handle_remove_readonly)
                    logger.info(f"Cleaned up temporary directory: {self.temp_dir}")
                except Exception as e:
                    logger.warning(f"Could not clean up temp directory: {e}")
    
    def run(self):
        """Run the agent to analyze files and push to GitHub."""
        try:
            print(f"GitAgent will process files from: {self.user_files_path}")
            print(f"Target GitHub repository: {self.github_repo_url}")
            
            # Get user confirmation
            user_input = input("\nEnter 'yes' to start the process: ")
            
            if user_input.lower() not in ['yes', 'y']:
                logger.info("Process canceled by user")
                print("Process canceled.")
                return False
            
            logger.info("Starting GitAgent process")
            print("\n=== Step 1: Analyzing Files ===")
            
            # Step 1: Analyze files
            file_data = self.analyze_files()
            if not file_data:
                logger.error("No files found to analyze")
                print("Error: No files found in the specified directory.")
                return False
            
            print(f"✓ Found {len(file_data)} files to process")
            
            print("\n=== Step 2: Generating README ===")
            
            # Step 2: Generate README
            if not self.generate_readme(file_data):
                logger.error("Failed to generate README")
                print("Error: Failed to generate README.md")
                return False
            
            print("✓ README.md generated successfully")
            
            print("\n=== Step 3: Pushing to GitHub ===")
            
            # Step 3: Push to GitHub
            if not self.push_to_github():
                logger.error("Failed to push to GitHub")
                print("Error: Failed to push to GitHub")
                return False
            
            print("✓ Successfully pushed to GitHub!")
            print(f"\nProcess completed! Repository updated at {self.github_repo_url}")
            return True
            
        except KeyboardInterrupt:
            logger.info("Process interrupted by user")
            print("\nProcess interrupted by user.")
            return False
        except Exception as e:
            logger.error(f"Error running GitAgent: {str(e)}")
            print(f"Error: {str(e)}")
            return False

if __name__ == "__main__":
    print("GitAgent - Automated Project Analysis and GitHub Push")
    print("=" * 50)
    
    agent = GitAgent()
    success = agent.run()
    
    if success:
        print("\n🎉 All done! Your project has been pushed to GitHub with a generated README.")
    else:
        print("\n❌ Process failed. Please check the logs for details.")
        sys.exit(1)