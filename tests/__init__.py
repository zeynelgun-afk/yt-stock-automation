"""All unit tests are offline; only transport boundary mocks temporarily opt out."""
import os
os.environ['YT_OFFLINE_TESTS'] = '1'
