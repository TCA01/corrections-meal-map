import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

// Mock Leaflet in JSDOM if needed
vi.mock('leaflet', () => {
  return {
    default: {
      map: vi.fn(() => ({
        setView: vi.fn(),
        getZoom: vi.fn(() => 7),
        remove: vi.fn(),
      })),
      tileLayer: vi.fn(() => ({
        addTo: vi.fn(),
      })),
      divIcon: vi.fn(() => ({})),
      marker: vi.fn(() => ({
        addTo: vi.fn().mockReturnThis(),
        bindPopup: vi.fn().mockReturnThis(),
        openPopup: vi.fn().mockReturnThis(),
        on: vi.fn().mockReturnThis(),
        remove: vi.fn(),
      })),
    },
  };
});
