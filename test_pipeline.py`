from chopcast.config import Settings
from chopcast.training.orchestrator import run_training
from chopcast.logging import configure, get_logger
import sys

def main():
    # 1. Load settings
    settings = Settings.load()

    # 2. Setup logging to see the orchestrator progress
    configure(settings.logging)
    log = get_logger(__name__)

    log.info("Starting full pipeline test via orchestrator...")

    try:
        # 3. Run the full pipeline
        # model_version: 'v1_test'
        # use_weather: False (starting with text-only to verify core pipeline)
        model_id = run_training(
            settings=settings,
            model_version="v1_test",
            use_weather=False
        )
        print(f"\n✅ Pipeline completed successfully!")
        print(f"Registered Model ID: {model_id}")
    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
