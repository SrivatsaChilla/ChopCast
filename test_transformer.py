from chopcast.config import Settings
from chopcast.training.orchestrator import run_training
from chopcast.logging import configure, get_logger
import sys

def main():
    # 1. Load settings
    settings = Settings.load()

    # 2. Setup logging
    configure(settings.logging)
    log = get_logger(__name__)

    log.info("Starting Transformer Fine-Tuning Pipeline...")

    try:
        # 3. Run the full pipeline with the Transformer model
        # model_version: 'v1_transformer'
        # model_kind: 'transformer'
        # use_weather: False (keeping it simple for first run)
        model_id = run_training(
            settings=settings,
            model_version="v1_transformer",
            use_weather=False,
            model_kind="transformer"
        )
        print(f"\nTransformer Pipeline completed successfully!")
        print(f"Registered Model ID: {model_id}")
    except Exception as e:
        print(f"\nPipeline failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
