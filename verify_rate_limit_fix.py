import asyncio
import logging
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from spam_detector.unified_email_analyzer import UnifiedEmailAnalyzer

# Configure simple logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

async def test_rpm_limit():
    print("\n--- Testing RPM Limiting ---")
    analyzer = UnifiedEmailAnalyzer()
    
    # Mock asyncio.sleep to not actually wait, but print
    with patch('asyncio.sleep') as mock_sleep:
        # Simulate 15 requests in rapid succession
        print("Simulating 15 requests...")
        for i in range(15):
            await analyzer.wait_for_rate_limit()
            # print(f"Request {i+1} allowed")
            
        # Check if sleep was called
        if mock_sleep.called:
            print("✅ SUCCESS: Rate limiter triggered sleep!")
            print(f"   Sleep called {mock_sleep.call_count} times.")
            print(f"   Last sleep duration: {mock_sleep.call_args[0][0] if mock_sleep.call_args else 'N/A'}")
        else:
            print("❌ FAILURE: Rate limiter did not sleep.")

async def test_retry_logic():
    print("\n--- Testing Retry Logic (429 - Single Key) ---")
    
    # Force single key to ensure we test the SLEEP behavior, not rotation
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "single_dummy_key"}):
        analyzer = UnifiedEmailAnalyzer()
        
        # Mock analyze_email to raise 429 then succeed
        # We need to return futures/awaitables
        f1 = asyncio.Future()
        f1.set_exception(Exception("429 RESOURCE_EXHAUSTED"))
        
        f2 = asyncio.Future()
        f2.set_result({"result": "success"})
        
        analyzer.analyze_email = MagicMock(side_effect=[f1, f2])
        
        with patch('asyncio.sleep') as mock_sleep:
            result = await analyzer.analyze_with_retry({}, "UTC")
            
            if result == {"result": "success"}:
                print("✅ SUCCESS: Retry logic handled 429 and eventually succeeded.")
                # Verify we waited roughly 20s
                if mock_sleep.call_count > 0:
                    waited = mock_sleep.call_args_list[0][0][0]
                    if waited >= 20: 
                        print(f"✅ SUCCESS: Waited appropriate time ({waited:.2f}s) for 429.")
                    else:
                        print(f"❌ FAILURE: Waited too little time ({waited:.2f}s) for 429.")
                else:
                    print("❌ FAILURE: Expected sleep but sleep was not called.")
            else:
                print("❌ FAILURE: Retry logic failed to return result.")


async def test_key_rotation():
    print("\n--- Testing API Key Rotation ---")
    
    # Mock environment to have 2 keys
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "key1,key2"}):
        analyzer = UnifiedEmailAnalyzer()
        
        # Verify keys loaded
        if len(analyzer.api_keys) == 2:
            print(f"✅ SUCCESS: Loaded 2 API keys correctly.")
        else:
            print(f"❌ FAILURE: Expected 2 keys, got {len(analyzer.api_keys)}")
            
        # Mock analyze_email to raise 429 on first key, success on second
        # Because we rebuild the model on rotation, we need to ensure the NEW model also has a mocked analyze?
        # Actually, analyze_email calls self.structured_llm.ainvoke.
        # We need to mock that deeper interaction or just mock analyze_email again if we can.
        # However, rotate_api_key rebuilds the LLM, so mocking analyze_email on the instance is fine 
        # because analyze_email is a method on the instance, not the LLM.
        
        # BUT, the real analyze_email calls self.structured_llm.ainvoke. 
        # If we mock analyze_email, we bypass the internal logic that calls rotate_api_key?
        # NO. analyze_with_retry calls analyze_email.
        # analyze_email does NOT catch the exception, it propagates it.
        # analyze_with_retry catches it and calls rotate_api_key.
        
        # So we can mock analyze_email to raise 429.
        f1 = asyncio.Future()
        f1.set_exception(Exception("429 RESOURCE_EXHAUSTED"))
        
        f2 = asyncio.Future()
        f2.set_result({"result": "success_with_key2"})
        
        analyzer.analyze_email = MagicMock(side_effect=[f1, f2])
        
        # We also need to mock _build_model so we don't actually try to create real Gemini clients with fake keys
        with patch.object(UnifiedEmailAnalyzer, '_build_model', return_value=MagicMock()) as mock_build:
             # The analyzer was already init'd, so current index is 0.
             
             # Call analyze_with_retry
             result = await analyzer.analyze_with_retry({}, "UTC")
             
             # Check if we got result
             if result == {"result": "success_with_key2"}:
                 print("✅ SUCCESS: Rotation logic returned success result.")
             else:
                 print(f"❌ FAILURE: result was {result}")
                 
             # Check if index rotated
             if analyzer.current_key_index == 1:
                 print(f"✅ SUCCESS: Key index rotated to 1.")
             else:
                 print(f"❌ FAILURE: Key index is {analyzer.current_key_index}")

async def main():
    await test_rpm_limit()
    await test_retry_logic()
    await test_key_rotation()

if __name__ == "__main__":
    asyncio.run(main())
