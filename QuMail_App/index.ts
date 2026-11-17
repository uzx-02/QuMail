import { registerRootComponent } from 'expo';
import { LogBox } from 'react-native';

// Suppress on-screen warning toast bars so they cannot cover the UI
LogBox.ignoreAllLogs(true);

import App from './App';

registerRootComponent(App);

