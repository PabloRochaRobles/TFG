// metro.config.js
//
// Configuración custom de Metro para Expo.
// - Integra `react-native-svg-transformer` para que los .svg importados
//   se conviertan en componentes React (necesario para el set Merida
//   de piezas de ajedrez en `assets/pieces/merida/`).
//
// Si en el futuro se añaden otros loaders custom, encadénalos aquí
// preservando la base de `expo/metro-config`.

const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

config.transformer = {
  ...config.transformer,
  babelTransformerPath: require.resolve('react-native-svg-transformer'),
};

config.resolver = {
  ...config.resolver,
  // El loader por defecto trataba .svg como asset binario. Lo sacamos
  // de `assetExts` para que el transformer entre en acción.
  assetExts: config.resolver.assetExts.filter((ext) => ext !== 'svg'),
  // …y lo añadimos como fuente para que Metro lo procese.
  sourceExts: [...config.resolver.sourceExts, 'svg'],
};

module.exports = config;
