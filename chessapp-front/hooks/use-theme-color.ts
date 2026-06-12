/**
 * Learn more about light and dark modes:
 * https://docs.expo.dev/guides/color-schemes/
 */

import { useTheme } from '@/contexts/ThemeContext';
import { Colors } from '../constants/Colors';

export function useThemeColors() {
  const { isDarkMode } = useTheme();
  return isDarkMode ? Colors.dark : Colors.light;
}
