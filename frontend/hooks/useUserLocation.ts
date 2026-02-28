import { useEffect, useState } from 'react';
import * as Location from 'expo-location';

export type Coords = {
  latitude: number;
  longitude: number;
};

export function useUserLocation() {
  const [coords, setCoords] = useState<Coords | null>(null);
  const [granted, setGranted] = useState(false);

  useEffect(() => {
    (async () => {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') return;
      setGranted(true);

      const location = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      const c = {
        latitude: location.coords.latitude,
        longitude: location.coords.longitude,
      };
      //log user coords to use for api calls!
      console.log('User coords:', c);
      setCoords(c);
    })();
  }, []);

  return { coords, granted };
}
