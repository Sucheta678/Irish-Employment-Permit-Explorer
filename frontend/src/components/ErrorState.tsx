interface ErrorStateProps {
  message?: string;
}

function ErrorState({
  message = "Something went wrong. Please try again.",
}: ErrorStateProps) {
  return (
    <div className="error-state" role="alert">
      {message}
    </div>
  );
}

export default ErrorState;