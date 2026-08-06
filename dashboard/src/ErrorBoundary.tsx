import React from "react";

type Props = {
  children: React.ReactNode;
};

type State = {
  error: Error | null;
};

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <main>
          <section className="error" role="alert">
            <strong>Dashboard rendering error</strong>
            <p>{this.state.error.message}</p>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}
