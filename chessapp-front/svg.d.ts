// Declaración de tipos para imports `.svg` procesados por
// `react-native-svg-transformer`. Cada SVG se expone como un
// componente React que acepta las props estándar de
// `react-native-svg/SvgProps`.
declare module '*.svg' {
  import type { FC } from 'react';
  import type { SvgProps } from 'react-native-svg';
  const content: FC<SvgProps>;
  export default content;
}
