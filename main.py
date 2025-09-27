# in drawing_analyzer/main.py

import asyncio
import json
import re
from pathlib import Path
from dotenv import load_dotenv

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Part, Content

# Import our custom orchestrator agent
from agents.orchestrator import DrawingAnalysisOrchestrator

# Load environment variables from the .env file
load_dotenv()

# Define constants for file paths
IMAGE_FOLDER = Path("images")
OUTPUT_FOLDER = Path("output")


async def analyze_drawing(image_paths: list[str], output_path: Path):
    """
    Main function to run the drawing analysis workflow for a single image set.
    """
    print(f"--- Starting analysis for: {image_paths[0]} ---")

    # 1. Prepare the services and the main agent
    session_service = InMemorySessionService()
    orchestrator_agent = DrawingAnalysisOrchestrator()

    runner = Runner(
        agent=orchestrator_agent,
        app_name="drawing_analyzer_app",
        session_service=session_service,
    )

    session = await session_service.create_session(
        app_name=runner.app_name, user_id="chief_engineer_user"
    )

    try:
        image_parts = []
        for image_path in image_paths:
            with open(image_path, "rb") as f:
                image_data = f.read()
            image_parts.append(Part(inline_data={'mime_type': 'image/png', 'data': image_data}))
        initial_message = Content(parts=image_parts)
    except FileNotFoundError as e:
        print(f"FATAL ERROR: Image file not found at '{e.filename}'")
        return

    print("\n--- Kicking off the ADK Runner... ---\n")
    final_report = ""

    async for event in runner.run_async(
        session_id=session.id,
        user_id=session.user_id,
        new_message=initial_message,
    ):
        print(f"EVENT from [{event.author}]:")
        if event.content and event.content.parts and event.content.parts[0].text:
            text_content = event.content.parts[0].text.strip()
            try:
                parsed_json = json.loads(text_content)
                print(json.dumps(parsed_json, indent=2))
            except (json.JSONDecodeError, TypeError):
                # Handle cases where the output might be wrapped in markdown
                if match := re.search(r"```json\s*(\{.*?\})\s*```", text_content, re.DOTALL):
                    cleaned_json = match.group(1)
                    try:
                        parsed_json = json.loads(cleaned_json)
                        print(json.dumps(parsed_json, indent=2))
                    except (json.JSONDecodeError, TypeError):
                        print(text_content) # Print raw if still fails
                else:
                    print(text_content)
        
        if event.is_final_response() and event.content:
            final_report = event.content.parts[0].text
        
        print("-" * 40)

    print("\n\n==================================================")
    print(f"      FINAL REPORT for {Path(image_paths[0]).name}")
    print("==================================================")
    
    # Save the final report to the output file
    try:
        # Clean the final report just in case
        if match := re.search(r"```json\s*(\{.*?\})\s*```", final_report, re.DOTALL):
            final_report = match.group(1)
        final_json = json.loads(final_report)
        print(json.dumps(final_json, indent=2))
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_json, f, indent=2)
    except (json.JSONDecodeError, TypeError):
        print("Could not parse the final report as JSON. Saving raw output.")
        print(final_report)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_report)
            
    print(f"\n--- Analysis complete. Report saved to: {output_path} ---")


def find_image_sets(folder: Path) -> set[str]:
    """Finds all unique image set base names in a folder."""
    base_names = set()
    for file_path in folder.glob("*.png"):
        # Use regex to remove '_pieceX' from the filename stem
        base_name = re.sub(r"_piece\d+$", "", file_path.stem)
        base_names.add(base_name)
    return base_names


if __name__ == "__main__":
    # Ensure the output directory exists
    OUTPUT_FOLDER.mkdir(exist_ok=True)

    # Find all unique drawing sets to process
    image_sets = find_image_sets(IMAGE_FOLDER)
    
    if not image_sets:
        print(f"FATAL ERROR: No image files (.png) found in the '{IMAGE_FOLDER}' directory.")
    else:
        print(f"Found {len(image_sets)} image set(s) to process.")

    for base_name in sorted(list(image_sets)):
        print("\n" + "="*80)
        output_file = OUTPUT_FOLDER / f"{base_name}.json"

        # Resume Logic: Skip if the output file already exists
        if output_file.exists():
            print(f"SKIPPING: Output for '{base_name}' already exists at '{output_file}'.")
            continue

        # Construct the list of 10 image paths for the current set
        main_image = IMAGE_FOLDER / f"{base_name}.png"
        image_paths = [str(main_image)] + [str(IMAGE_FOLDER / f"{base_name}_piece{i}.png") for i in range(1, 10)]

        # Verify all files exist before starting
        missing_files = [p for p in image_paths if not Path(p).exists()]
        if missing_files:
            print(f"FATAL ERROR: The following image files are missing for set '{base_name}':")
            for p in missing_files:
                print(f"- {p}")
        else:
            # Run the main asynchronous function for the current set
            try:
                asyncio.run(analyze_drawing(image_paths, output_file))
            except Exception as e:
                print(f"\n!!!!!!!! An unexpected error occurred while processing {base_name} !!!!!!!!")
                print(f"Error: {e}")
                print("Moving to the next image set.")