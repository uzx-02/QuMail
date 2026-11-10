import React from 'react';

interface ShinyTextProps {
  text: string;
  disabled?: boolean;
  speed?: number;
  className?: string;
}

export const ShinyText: React.FC<ShinyTextProps> = ({
  text,
  disabled = false,
  speed = 4,
  className = '',
}) => {
  const animationDuration = `${speed}s`;

  if (disabled) {
    return <span className={className}>{text}</span>;
  }

  return (
    <span
      className={`inline-block relative text-transparent bg-clip-text bg-gradient-to-r from-blue-600 via-indigo-300 to-blue-600 dark:from-indigo-400 dark:via-white dark:to-indigo-400 bg-[length:200%_100%] animate-shimmer font-semibold ${className}`}
      style={{ animationDuration }}
    >
      {text}
    </span>
  );
};
