import { Component, type ErrorInfo, type ReactNode } from "react";
import { Alert, Button, Stack, Text } from "@mantine/core";
import i18n from "../i18n";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Catches render errors so one broken page does not blank the whole SPA. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("UI error boundary", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <Stack p="xl" maw={640} mx="auto" gap="md">
          <Alert color="red" title={i18n.t("errorBoundary.title")}>
            <Text size="sm" mb="sm">
              {this.state.error.message || String(this.state.error)}
            </Text>
            <Button
              size="xs"
              variant="light"
              onClick={() => {
                this.setState({ error: null });
                window.location.assign("/");
              }}
            >
              {i18n.t("errorBoundary.home")}
            </Button>
          </Alert>
        </Stack>
      );
    }
    return this.props.children;
  }
}
