import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Anchor,
  Blockquote,
  Code,
  Divider,
  List,
  ScrollArea,
  Table,
  Text,
  Title,
} from "@mantine/core";

/**
 * Markdown от модели (GFM: таблицы, списки, код). HTML не рендерится —
 * react-markdown экранирует его по умолчанию, поэтому ответ агента безопасен.
 */
export function Markdown({ children }: { children: string }): ReactNode {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children: text }) => (
          <Text size="sm" my={4} style={{ whiteSpace: "pre-wrap" }}>
            {text}
          </Text>
        ),
        a: ({ children: text, href }) => (
          <Anchor href={href} target="_blank" rel="noreferrer noopener" size="sm">
            {text}
          </Anchor>
        ),
        h1: ({ children: text }) => <Title order={4}>{text}</Title>,
        h2: ({ children: text }) => <Title order={5}>{text}</Title>,
        h3: ({ children: text }) => <Title order={6}>{text}</Title>,
        ul: ({ children: items }) => (
          <List size="sm" spacing={2} withPadding listStyleType="disc">
            {items}
          </List>
        ),
        ol: ({ children: items }) => (
          <List size="sm" spacing={2} withPadding listStyleType="decimal">
            {items}
          </List>
        ),
        li: ({ children: items }) => <List.Item>{items}</List.Item>,
        pre: ({ children: body }) => <>{body}</>,
        code: ({ className, children: body }) => {
          const text = String(body ?? "");
          const block = Boolean(className?.includes("language-")) || text.includes("\n");
          return block ? (
            <Code block style={{ whiteSpace: "pre-wrap" }}>
              {text}
            </Code>
          ) : (
            <Code>{text}</Code>
          );
        },
        blockquote: ({ children: body }) => <Blockquote p="xs">{body}</Blockquote>,
        hr: () => <Divider my="sm" />,
        table: ({ children: body }) => (
          <ScrollArea type="auto" my="xs">
            <Table striped withTableBorder highlightOnHover miw={420}>
              {body}
            </Table>
          </ScrollArea>
        ),
        thead: ({ children: body }) => <Table.Thead>{body}</Table.Thead>,
        tbody: ({ children: body }) => <Table.Tbody>{body}</Table.Tbody>,
        tr: ({ children: body }) => <Table.Tr>{body}</Table.Tr>,
        th: ({ children: body }) => <Table.Th>{body}</Table.Th>,
        td: ({ children: body }) => <Table.Td>{body}</Table.Td>,
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
