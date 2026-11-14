import React from 'react';
import UseAnimations from 'react-useanimations';
import checkBox from 'react-useanimations/lib/checkBox';

export interface CheckboxProps {
  checked: boolean;
  indeterminate?: boolean;
  onChange?: (checked: boolean, event?: React.MouseEvent) => void;
  onClick?: (event: React.MouseEvent) => void;
  disabled?: boolean;
  size?: number;
  label?: React.ReactNode;
  title?: string;
  className?: string;
  strokeColor?: string;
}

export const Checkbox: React.FC<CheckboxProps> = ({
  checked,
  indeterminate,
  onChange,
  onClick,
  disabled = false,
  size = 22,
  label,
  title,
  className = '',
  strokeColor,
}) => {
  const isChecked = checked || Boolean(indeterminate);

  const handleClick = (e: React.MouseEvent) => {
    if (disabled) return;
    onClick?.(e);
    onChange?.(!checked, e);
  };

  const resolvedStrokeColor =
    strokeColor || (isChecked ? 'var(--qumail-accent, #0B57D0)' : 'currentColor');

  const iconElement = (
    <div
      role="checkbox"
      aria-checked={indeterminate ? 'mixed' : checked}
      aria-disabled={disabled}
      title={title}
      onClick={handleClick}
      className={`inline-flex items-center justify-center shrink-0 select-none cursor-pointer ${
        disabled ? 'opacity-40 cursor-not-allowed' : 'active:scale-95 transition-transform'
      } ${
        isChecked
          ? 'text-[#0B57D0] dark:text-sky-400'
          : 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300'
      } ${className}`}
    >
      <UseAnimations
        animation={checkBox}
        size={size}
        active={isChecked}
        strokeColor={resolvedStrokeColor}
      />
    </div>
  );

  if (!label) {
    return iconElement;
  }

  return (
    <label
      onClick={handleClick}
      title={title}
      className={`inline-flex items-center space-x-1 cursor-pointer select-none text-xs font-semibold ${
        disabled ? 'opacity-40 cursor-not-allowed' : ''
      }`}
    >
      {iconElement}
      <span className="text-[#202124] dark:text-[#F1F5F9]">{label}</span>
    </label>
  );
};

export default Checkbox;
